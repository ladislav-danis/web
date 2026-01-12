"""
Simple, elegant templating.
(Part of web.py)

Template Design:

A template string is split into tokens, which are then combined into nodes. The
parse tree is a nodelist. TextNode and ExpressionNode are simple nodes, while
constructs like for-loops and if-conditions are block nodes containing child nodes.

Each node can emit a Python string. The Python string emitted by the root node
is validated for safety and then executed in the given environment.

Care is taken to match the generated code line-for-line with the template,
so that error messages can point to the exact line number in the template file
(though this may not work in all complex cases).

Grammar:

    template -> defwith sections
    defwith -> '$def with (' arguments ')' | ''
    sections -> section*
    section -> block | assignment | line

    assignment -> '$ ' <assignment expression>
    line -> (text|expr)*
    text -> <any characters other than $>
    expr -> '$' pyexpr | '$(' pyexpr ')' | '${' pyexpr '}'
    pyexpr -> <python expression>
"""

import ast
import builtins
import glob
import itertools
import logging
import os
import sys
import token
import tokenize
from collections.abc import MutableMapping
from functools import partial
from typing import (
    Any,
    Callable,
    Dict,
    Iterator,
    List,
    Optional,
    Tuple,
    Type,
    Union,
)

from more_itertools import peekable

from .net import websafe
from .utils import re_compile, safestr, safeunicode, storage
from .webapi import config

__all__ = [
    "Template",
    "Render",
    "render",
    "frender",
    "ParseError",
    "SecurityError",
    "test",
]


def splitline(text: str) -> Tuple[str, str]:
    """Splits the given text at the first newline character.

    Args:
        text (str): The input string to split.

    Returns:
        Tuple[str, str]: A tuple where the first element is the first line
        (including the newline character) and the second element is the
        remainder of the string.

    Examples:
        >>> splitline('foo\\nbar')
        ('foo\\n', 'bar')
        >>> splitline('foo')
        ('foo', '')
        >>> splitline('')
        ('', '')
    """
    index = text.find("\n") + 1
    if index:
        return text[:index], text[index:]
    else:
        return text, ""


class Parser:
    """Parses a template string into a tree of nodes."""

    def __init__(self) -> None:
        """Initializes the parser with statement nodes and keywords."""
        self.statement_nodes: Dict[str, Type[BlockNode]] = STATEMENT_NODES
        self.keywords: List[str] = KEYWORDS

    def parse(self, text: str, name: str = "<template>") -> "DefwithNode":
        """Parses the template text into a node tree.

        Args:
            text (str): The template string.
            name (str): The filename or name of the template for error reporting.

        Returns:
            DefwithNode: The root node of the parsed template tree.
        """
        self.text = text
        self.name = name

        defwith, text = self.read_defwith(text)
        suite = self.read_suite(text)
        return DefwithNode(defwith, suite)

    def read_defwith(self, text: str) -> Tuple[str, str]:
        """Reads the optional '$def with (...)' line from the template.

        Args:
            text (str): The template string.

        Returns:
            Tuple[str, str]: A tuple containing the 'def with' statement and
            the rest of the template text.
        """
        if text.startswith("$def with"):
            defwith, text = splitline(text)
            defwith = defwith[1:].strip()  # strip $ and spaces
            return defwith, text
        else:
            return "", text

    def read_section(self, text: str) -> Tuple[Any, str]:
        """Reads one section from the given text.

        A section can be a block (if, for), an assignment, or a simple line.

        Args:
            text (str): The remaining template text to parse.

        Returns:
            Tuple[Any, str]: A tuple containing the parsed Node and the
            rest of the template text.

        Examples:
            >>> read_section = Parser().read_section
            >>> read_section('foo\\nbar\\n')
            (<line: [t'foo\\n']>, 'bar\\n')
            >>> read_section('$ a = b + 1\\nfoo\\n')
            (<assignment: 'a = b + 1'>, 'foo\\n')
        """
        if text.lstrip(" ").startswith("$"):
            index = text.index("$")
            begin_indent, text2 = text[:index], text[index + 1 :]
            ahead = self.python_lookahead(text2)

            if ahead == "var":
                return self.read_var(text2)
            elif ahead in self.statement_nodes:
                return self.read_block_section(text2, begin_indent)
            elif ahead in self.keywords:
                return self.read_keyword(text2)
            elif ahead.strip() == "":
                # assignments start with a space after $
                return self.read_assignment(text2)
        return self.readline(text)

    def read_var(self, text: str) -> Tuple["VarNode", str]:
        """Reads a '$var' statement.

        Args:
            text (str): The template text starting with 'var...'.

        Returns:
            Tuple[VarNode, str]: The parsed VarNode and the remaining text.

        Raises:
            SyntaxError: If the var statement is malformed.

        Examples:
            >>> read_var = Parser().read_var
            >>> read_var('var x=10\\nfoo')
            (<var: x = 10>, 'foo')
            >>> read_var('var x: hello $name\\nfoo')
            (<var: x = join_(u'hello ', escape_(name, True))>, 'foo')
        """
        line, text = splitline(text)
        tokens = self.python_tokens(line)
        if len(tokens) < 4:
            raise SyntaxError("Invalid var statement")

        name = tokens[1]
        sep = tokens[2]
        value = line.split(sep, 1)[1].strip()

        if sep == "=":
            pass  # no need to process value
        elif sep == ":":
            if tokens[3] == "\n":  # multi-line var statement
                block, text = self.read_indented_block(text, "    ")
                lines = [self.readline(x)[0] for x in block.splitlines()]
                nodes = []
                for x in lines:
                    nodes.extend(x.nodes)
                    nodes.append(TextNode("\n"))
            else:  # single-line var statement
                linenode, _ = self.readline(value)
                nodes = linenode.nodes
            parts = [node.emit("") for node in nodes]
            value = "join_(%s)" % ", ".join(parts)
        else:
            raise SyntaxError("Invalid var statement")
        return VarNode(name, value), text

    def read_suite(self, text: str) -> "SuiteNode":
        """Reads sections one by one until the end of the text.

        Args:
            text (str): The template text to parse.

        Returns:
            SuiteNode: A node containing a list of all parsed sections.

        Examples:
            >>> read_suite = Parser().read_suite
            >>> read_suite('hello $name\\nfoo\\n')
            [<line: [t'hello ', $name, t'\\n']>, <line: [t'foo\\n']>]
        """
        sections = []
        while text:
            section, text = self.read_section(text)
            sections.append(section)
        return SuiteNode(sections)

    def readline(self, text: str) -> Tuple["LineNode", str]:
        """Reads one line, handling backslash for line continuation.

        Args:
            text (str): The template text.

        Returns:
            Tuple[LineNode, str]: A node representing the line and the
            remaining text.

        Examples:
            >>> readline = Parser().readline
            >>> readline('hello $name!\\nbye!')
            (<line: [t'hello ', $name, t'!\\n']>, 'bye!')
            >>> readline('hello $name!\\\\\\nbye!')
            (<line: [t'hello ', $name, t'!']>, 'bye!')
        """
        line, text = splitline(text)

        if line.endswith("\\\n"):
            line = line[:-2]

        nodes = []
        while line:
            node, line = self.read_node(line)
            nodes.append(node)

        return LineNode(nodes), text

    def read_node(self, text: str) -> Tuple[Union["TextNode", "ExpressionNode"], str]:
        """Reads a single node (text or expression) from a line.

        Args:
            text (str): The text of a line.

        Returns:
            Tuple[Union[TextNode, ExpressionNode], str]: The parsed node and
            the remaining text of the line.

        Examples:
            >>> read_node = Parser().read_node
            >>> read_node('hello $name')
            (t'hello ', '$name')
            >>> read_node('$name')
            ($name, '')
        """
        if text.startswith("$$"):
            return TextNode("$"), text[2:]
        elif text.startswith("$#"):  # comment
            line, text = splitline(text)
            return TextNode("\n"), text
        elif text.startswith("$"):
            text = text[1:]  # strip $
            if text.startswith(":"):
                escape = False
                text = text[1:]  # strip :
            else:
                escape = True
            return self.read_expr(text, escape=escape)
        else:
            return self.read_text(text)

    def read_text(self, text: str) -> Tuple["TextNode", str]:
        """Reads a plain text node.

        Args:
            text (str): The input text.

        Returns:
            Tuple[TextNode, str]: A TextNode and the remaining text after it.

        Examples:
            >>> read_text = Parser().read_text
            >>> read_text('hello $name')
            (t'hello ', '$name')
        """
        index = text.find("$")
        if index < 0:
            return TextNode(text), ""
        else:
            return TextNode(text[:index]), text[index:]

    def read_keyword(self, text: str) -> Tuple["StatementNode", str]:
        """Reads a keyword statement like 'break' or 'continue'.

        Args:
            text (str): The template text starting with the keyword.

        Returns:
            Tuple[StatementNode, str]: The parsed node and remaining text.
        """
        line, text = splitline(text)
        return StatementNode(line.strip() + "\n"), text

    def read_expr(
        self, text: str, escape: bool = True
    ) -> Tuple["ExpressionNode", str]:  # noqa: C901, PLR0915
        """Reads a Python expression from the text.

        This handles simple variables, attribute access, and balanced parentheses.

        Args:
            text (str): The text starting after the '$'.
            escape (bool): Whether the output of the expression should be escaped.

        Returns:
            Tuple[ExpressionNode, str]: The parsed expression node and the
            remaining text.

        Examples:
            >>> read_expr = Parser().read_expr
            >>> read_expr("name")
            ($name, '')
            >>> read_expr("a.b and c")
            ($a.b, ' and c')
            >>> read_expr('a[1].f(2) done.')
            ($a[1].f(2), ' done.')
        """

        def simple_expr() -> None:
            identifier()
            extended_expr()

        def identifier() -> Any:
            return next(tokens)

        def extended_expr() -> None:
            lookahead = tokens.peek()
            if lookahead is None:
                return
            elif lookahead.value == ".":
                attr_access()
            elif lookahead.value in parens:
                paren_expr()
                extended_expr()
            else:
                return

        def attr_access() -> None:
            if tokens[1].type == token.NAME:
                next(tokens)  # consume dot
                identifier()
                extended_expr()

        def paren_expr() -> None:
            begin = next(tokens).value
            end = parens[begin]
            while True:
                if tokens.peek().value in parens:
                    paren_expr()
                else:
                    t = next(tokens)
                    if t.value == end:
                        break

        parens = {"(": ")", "[": "]", "{": "}"}

        def get_tokens(text: str) -> Iterator[storage]:
            def tokenize_text(input_text: str) -> Iterator[storage]:
                i = iter([input_text])
                readline = lambda: next(i)
                end = None
                for t in tokenize.generate_tokens(readline):
                    t_storage = storage(type=t[0], value=t[1], begin=t[2], end=t[3])
                    if end is not None and end != t_storage.begin:
                        _, x1 = end
                        _, x2 = t_storage.begin
                        yield storage(
                            type=-1,
                            value=input_text[x1:x2],
                            begin=end,
                            end=t_storage.begin,
                        )
                    end = t_storage.end
                    yield t_storage

            try:
                yield from tokenize_text(text)
            except tokenize.TokenError as e:
                error_pos = e.args[1][1] - 1
                fixed_text = text[0:error_pos]
                yield from itertools.chain(
                    tokenize_text(fixed_text),
                    error_token_generator(text, error_pos + 1, len(text)),
                )

        def error_token_generator(text: str, start: int, end: int) -> Iterator[storage]:
            yield storage(
                type=token.ERRORTOKEN, value=text[start:], begin=start, end=end
            )

        class peekable2(peekable):
            def __init__(self, iterable: Iterator) -> None:
                super().__init__(iterable)
                self.current_item: Optional[storage] = None

            def __next__(self) -> storage:
                self.current_item = super().__next__()
                return self.current_item

        tokens = peekable2(get_tokens(text))

        if tokens.peek().value in parens:
            paren_expr()
        else:
            simple_expr()
        row, col = tokens.current_item.end
        return ExpressionNode(text[:col], escape=escape), text[col:]

    def read_assignment(self, text: str) -> Tuple["AssignmentNode", str]:
        """Reads an assignment statement from the text.

        Args:
            text (str): The text starting after '$ '.

        Returns:
            Tuple[AssignmentNode, str]: The parsed node and remaining text.

        Examples:
            >>> read_assignment = Parser().read_assignment
            >>> read_assignment('a = b + 1\\nfoo')
            (<assignment: 'a = b + 1'>, 'foo')
        """
        line, text = splitline(text)
        return AssignmentNode(line.strip()), text

    def python_lookahead(self, text: str) -> str:
        """Returns the first Python token from the given text.

        Args:
            text (str): The input string.

        Returns:
            str: The value of the first token.

        Examples:
            >>> python_lookahead = Parser().python_lookahead
            >>> python_lookahead('for i in range(10):')
            'for'
        """
        i = iter([text])
        readline = lambda: next(i)
        tokens = tokenize.generate_tokens(readline)
        return next(tokens)[1]

    def python_tokens(self, text: str) -> List[str]:
        """Tokenizes a string and returns a list of token values.

        Args:
            text (str): The string to tokenize.

        Returns:
            List[str]: A list of the token string values.
        """
        i = iter([text])
        readline = lambda: next(i)
        tokens = tokenize.generate_tokens(readline)
        return [t[1] for t in tokens]

    def read_indented_block(self, text: str, indent: str) -> Tuple[str, str]:
        """Reads a block of text with a specific indentation.

        Args:
            text (str): The template text.
            indent (str): The indentation string to expect for the block.

        Returns:
            Tuple[str, str]: A tuple containing the text of the block
            (with indentation removed) and the remaining template text.

        Examples:
            >>> read_indented_block = Parser().read_indented_block
            >>> read_indented_block('  a\\n  b\\nc', '  ')
            ('a\\nb\\n', 'c')
        """
        if indent == "":
            return "", text

        block = ""
        while text:
            line, text2 = splitline(text)
            if line.strip() == "":
                block += "\n"
            elif line.startswith(indent):
                block += line[len(indent) :]
            else:
                break
            text = text2
        return block, text

    def read_statement(self, text: str) -> Tuple[str, str]:
        """Reads a Python statement ending with a colon.

        Args:
            text (str): The line of text containing the statement.

        Returns:
            Tuple[str, str]: The statement part and the rest of the line.

        Examples:
            >>> read_statement = Parser().read_statement
            >>> read_statement('for i in range(10): hello $name')
            ('for i in range(10):', ' hello $name')
        """
        tok = PythonTokenizer(text)
        tok.consume_till(":")
        return text[: tok.index], text[tok.index :]

    def read_block_section(
        self, text: str, begin_indent: str = ""
    ) -> Tuple["BlockNode", str]:
        """Reads a block section (e.g., if, for) and its content.

        Args:
            text (str): The template text starting after '$'.
            begin_indent (str): The indentation of the block statement itself.

        Returns:
            Tuple[BlockNode, str]: The parsed block node and remaining text.

        Examples:
            >>> read_block_section = Parser().read_block_section
            >>> read_block_section('for i in range(10): hello $i\\nfoo')
            (<block: 'for i in range(10):', [<line: [t'hello ', $i, t'\\n']>]>, 'foo')
        """
        line, text = splitline(text)
        stmt, line = self.read_statement(line)
        keyword = self.python_lookahead(stmt)

        if line.strip() and not line.lstrip().startswith("$#"):
            block = line.lstrip()
        else:

            def find_indent(text: str) -> str:
                rx = re_compile("  +")
                match = rx.match(text)
                return (match and match.group(0)) or ""

            first_indent = find_indent(text)[len(begin_indent) :]

            if keyword == "code":
                indent = begin_indent + first_indent
            else:
                indent = begin_indent + min(first_indent, INDENT)

            block, text = self.read_indented_block(text, indent)

        return self.create_block_node(keyword, stmt, block, begin_indent), text

    def create_block_node(
        self, keyword: str, stmt: str, block: str, begin_indent: str
    ) -> "BlockNode":
        """Factory method to create a specific type of BlockNode.

        Args:
            keyword (str): The keyword of the block (e.g., 'for', 'if').
            stmt (str): The full statement string.
            block (str): The content of the block.
            begin_indent (str): The indentation of the block statement.

        Returns:
            BlockNode: An instance of a BlockNode subclass.

        Raises:
            ParseError: If the keyword is unknown.
        """
        if keyword in self.statement_nodes:
            return self.statement_nodes[keyword](stmt, block, begin_indent)
        else:
            raise ParseError(f"Unknown statement: {repr(keyword)}")


class PythonTokenizer:
    """Utility wrapper over Python's `tokenize` module."""

    def __init__(self, text: str) -> None:
        """Initializes the tokenizer.

        Args:
            text (str): The Python code string to tokenize.
        """
        self.text = text
        i = iter([text])
        readline = lambda: next(i)
        self.tokens: Iterator[tokenize.TokenInfo] = tokenize.generate_tokens(readline)
        self.index = 0

    def consume_till(self, delim: str) -> None:
        """Consumes tokens until a specific delimiter is found.

        Handles nested parentheses, brackets, and braces.

        Args:
            delim (str): The delimiter token value to stop at (e.g., ':').

        Examples:
            >>> tok = PythonTokenizer('for i in range(10): hello')
            >>> tok.consume_till(':')
            >>> tok.text[:tok.index]
            'for i in range(10):'
        """
        try:
            while True:
                t = next(self)
                if t.value == delim:
                    break
                elif t.value == "(":
                    self.consume_till(")")
                elif t.value == "[":
                    self.consume_till("]")
                elif t.value == "{":
                    self.consume_till("}")
                if t.value == "\n":
                    break
        except StopIteration:
            # Error will be caught by Python compiler later
            return

    def __next__(self) -> storage:
        """Gets the next token as a storage object."""
        tok_info = next(self.tokens)
        _row, col = tok_info.end
        self.index = col
        return storage(
            type=tok_info.type,
            value=tok_info.string,
            begin=tok_info.start,
            end=tok_info.end,
        )


class DefwithNode:
    """Represents the root of a template, including the '$def with' line."""

    def __init__(self, defwith: str, suite: "SuiteNode") -> None:
        """Initializes the DefwithNode.

        Args:
            defwith (str): The '$def with' statement string.
            suite (SuiteNode): The node containing the body of the template.
        """
        if defwith:
            self.defwith = defwith.replace("with", "__template__") + ":"
            self.defwith += "\n    _lineoffset_ = -4"
        else:
            self.defwith = "def __template__():"
            self.defwith += "\n    _lineoffset_ = -5"

        self.defwith += "\n    loop = ForLoop()"
        self.defwith += "\n    self = TemplateResult(); extend_ = self.extend"
        self.suite = suite
        self.end = "\n    return self"

    def emit(self, indent: str) -> str:
        """Emits the complete Python code for the template.

        Args:
            indent (str): The base indentation for the generated code.

        Returns:
            str: The full, executable Python code string for the template.
        """
        encoding = "# coding: utf-8\n"
        return encoding + self.defwith + self.suite.emit(indent + INDENT) + self.end

    def __repr__(self) -> str:
        """Returns a string representation of the node."""
        return f"<defwith: {self.defwith}, {self.suite}>"


class TextNode:
    """Represents a plain text segment in the template."""

    def __init__(self, value: str) -> None:
        """Initializes the TextNode.

        Args:
            value (str): The string value of the text.
        """
        self.value = value

    def emit(self, indent: str, begin_indent: str = "") -> str:
        """Emits the Python representation of the text (a quoted string).

        Args:
            indent (str): Indentation (ignored for this node).
            begin_indent (str): Indentation (ignored for this node).

        Returns:
            str: A Python string literal.
        """
        return repr(safeunicode(self.value))

    def __repr__(self) -> str:
        """Returns a string representation of the node."""
        return "t" + repr(self.value)


class ExpressionNode:
    """Represents a Python expression to be evaluated (e.g., $name)."""

    def __init__(self, value: str, escape: bool = True) -> None:
        """Initializes the ExpressionNode.

        Args:
            value (str): The Python expression string.
            escape (bool): If True, the result will be HTML-escaped.
        """
        self.value = value.strip()
        if value.startswith("{") and value.endswith("}"):
            self.value = "(" + self.value[1:-1] + ")"
        self.escape = escape

    def emit(self, indent: str, begin_indent: str = "") -> str:
        """Emits the Python code to evaluate and escape the expression.

        Args:
            indent (str): Indentation (ignored).
            begin_indent (str): Indentation (ignored).

        Returns:
            str: Python code calling the `escape_` helper function.
        """
        return f"escape_({self.value}, {bool(self.escape)})"

    def __repr__(self) -> str:
        """Returns a string representation of the node."""
        escape_char = "" if self.escape else ":"
        return f"${escape_char}{self.value}"


class AssignmentNode:
    """Represents an assignment statement (e.g., '$ a = 1')."""

    def __init__(self, code: str) -> None:
        """Initializes the AssignmentNode.

        Args:
            code (str): The assignment code string.
        """
        self.code = code

    def emit(self, indent: str, begin_indent: str = "") -> str:
        """Emits the indented assignment code.

        Args:
            indent (str): The indentation to apply.
            begin_indent (str): Indentation (ignored).

        Returns:
            str: The indented Python assignment statement.
        """
        return indent + self.code + "\n"

    def __repr__(self) -> str:
        """Returns a string representation of the node."""
        return f"<assignment: {repr(self.code)}>"


class LineNode:
    """Represents a single line in the template, containing multiple nodes."""

    def __init__(self, nodes: List[Union[TextNode, ExpressionNode]]) -> None:
        """Initializes the LineNode.

        Args:
            nodes (List[Union[TextNode, ExpressionNode]]): A list of nodes
                that make up the line.
        """
        self.nodes = nodes

    def emit(self, indent: str, text_indent: str = "", name: str = "") -> str:
        """Emits Python code to generate the output for this line.

        Args:
            indent (str): The base indentation for the `extend_` call.
            text_indent (str): Prepended indentation for the line's output.
            name (str): Unused parameter.

        Returns:
            str: A Python statement calling `extend_` with the line's content.
        """
        text = [node.emit("") for node in self.nodes]
        if text_indent:
            text = [repr(text_indent)] + text
        return indent + "extend_([%s])\n" % ", ".join(text)

    def __repr__(self) -> str:
        """Returns a string representation of the node."""
        return f"<line: {repr(self.nodes)}>"


INDENT = "    "  # 4 spaces


class BlockNode:
    """Base class for block statements like 'if', 'for', 'while'."""

    def __init__(self, stmt: str, block: str, begin_indent: str = "") -> None:
        """Initializes the BlockNode.

        Args:
            stmt (str): The statement part (e.g., 'if x > 0:').
            block (str): The text content inside the block.
            begin_indent (str): The indentation of the block statement itself.
        """
        self.stmt = stmt
        self.suite = Parser().read_suite(block)
        self.begin_indent = begin_indent

    def emit(self, indent: str, text_indent: str = "") -> str:
        """Emits the Python code for the block statement and its suite.

        Args:
            indent (str): The base indentation for the statement.
            text_indent (str): Indentation to be passed to child nodes.

        Returns:
            str: The generated Python code for the block.
        """
        text_indent = self.begin_indent + text_indent
        out = indent + self.stmt + self.suite.emit(indent + INDENT, text_indent)
        return out

    def __repr__(self) -> str:
        """Returns a string representation of the node."""
        return f"<block: {repr(self.stmt)}, {repr(self.suite)}>"


class ForNode(BlockNode):
    """Represents a 'for' loop, with special handling for `loop` variable."""

    def __init__(self, stmt: str, block: str, begin_indent: str = "") -> None:
        """Initializes the ForNode.

        Args:
            stmt (str): The original 'for' statement.
            block (str): The content of the loop.
            begin_indent (str): The indentation of the 'for' statement.
        """
        self.original_stmt = stmt
        tok = PythonTokenizer(stmt)
        tok.consume_till("in")
        a = stmt[: tok.index]  # 'for i in' part
        b = stmt[tok.index : -1]  # iterable part
        modified_stmt = a + " loop.setup(" + b.strip() + "):"
        super().__init__(modified_stmt, block, begin_indent)

    def __repr__(self) -> str:
        """Returns a string representation of the node."""
        return f"<block: {repr(self.original_stmt)}, {repr(self.suite)}>"


class CodeNode:
    """Represents a '$code' block for embedding raw Python code."""

    def __init__(self, stmt: str, block: str, begin_indent: str = "") -> None:
        """Initializes the CodeNode.

        Args:
            stmt (str): The '$code' statement (ignored).
            block (str): The raw Python code to be embedded.
            begin_indent (str): Indentation (ignored).
        """
        self.code = "\n" + block

    def emit(self, indent: str, text_indent: str = "") -> str:
        """Emits the indented raw Python code.

        Args:
            indent (str): The indentation to apply to each line of the code.
            text_indent (str): Indentation (ignored).

        Returns:
            str: The formatted Python code block.
        """
        rx = re.compile("^", re.M)
        return rx.sub(indent, self.code).rstrip(" ")

    def __repr__(self) -> str:
        """Returns a string representation of the node."""
        return f"<code: {repr(self.code)}>"


class StatementNode:
    """Represents a simple one-line statement like 'break' or 'pass'."""

    def __init__(self, stmt: str) -> None:
        """Initializes the StatementNode.

        Args:
            stmt (str): The statement string.
        """
        self.stmt = stmt

    def emit(self, indent: str, begin_indent: str = "") -> str:
        """Emits the indented statement.

        Args:
            indent (str): The indentation to apply.
            begin_indent (str): Indentation (ignored).

        Returns:
            str: The indented Python statement.
        """
        return indent + self.stmt

    def __repr__(self) -> str:
        """Returns a string representation of the node."""
        return f"<stmt: {repr(self.stmt)}>"


class IfNode(BlockNode):
    """Represents an 'if' block."""

    pass


class ElseNode(BlockNode):
    """Represents an 'else' block."""

    pass


class ElifNode(BlockNode):
    """Represents an 'elif' block."""

    pass


class DefNode(BlockNode):
    """Represents a '$def' block for defining functions inside a template."""

    def __init__(self, *a: Any, **kw: Any) -> None:
        """Initializes the DefNode, injecting setup and return code."""
        super().__init__(*a, **kw)

        # Prepend code to initialize a new TemplateResult for the function
        setup_code = CodeNode("", "")
        setup_code.code = "self = TemplateResult(); extend_ = self.extend\n"
        self.suite.sections.insert(0, setup_code)

        # Append code to return the TemplateResult
        return_code = CodeNode("", "")
        return_code.code = "return self\n"
        self.suite.sections.append(return_code)

    def emit(self, indent: str, text_indent: str = "") -> str:
        """Emits the Python code for the function definition.

        Args:
            indent (str): The base indentation.
            text_indent (str): Indentation passed to child nodes.

        Returns:
            str: The generated Python function definition.
        """
        text_indent = self.begin_indent + text_indent
        out = indent + self.stmt + self.suite.emit(indent + INDENT, text_indent)
        # Adjust line offset for accurate error reporting
        return indent + "_lineoffset_ -= 3\n" + out


class VarNode:
    """Represents a '$var' statement for setting attributes on the result."""

    def __init__(self, name: str, value: str) -> None:
        """Initializes the VarNode.

        Args:
            name (str): The name of the variable.
            value (str): The string representation of the value to be assigned.
        """
        self.name = name
        self.value = value

    def emit(self, indent: str, text_indent: str) -> str:
        """Emits Python code to set an attribute on the 'self' (TemplateResult).

        Args:
            indent (str): The indentation for the assignment.
            text_indent (str): Indentation (ignored).

        Returns:
            str: The Python assignment statement.
        """
        return indent + f"self[{repr(self.name)}] = {self.value}\n"

    def __repr__(self) -> str:
        """Returns a string representation of the node."""
        return f"<var: {self.name} = {self.value}>"


class SuiteNode:
    """Represents a suite of sections (the body of a block or template)."""

    def __init__(self, sections: List[Any]) -> None:
        """Initializes the SuiteNode.

        Args:
            sections (List[Any]): A list of Node objects.
        """
        self.sections = sections

    def emit(self, indent: str, text_indent: str = "") -> str:
        """Emits the combined Python code for all sections in the suite.

        Args:
            indent (str): The base indentation for the sections.
            text_indent (str): Indentation passed to child nodes.

        Returns:
            str: The concatenated Python code from all child nodes.
        """
        return "\n" + "".join([s.emit(indent, text_indent) for s in self.sections])

    def __repr__(self) -> str:
        """Returns a string representation of the node."""
        return repr(self.sections)


STATEMENT_NODES: Dict[str, Type[BlockNode]] = {
    "for": ForNode,
    "while": BlockNode,
    "if": IfNode,
    "elif": ElifNode,
    "else": ElseNode,
    "def": DefNode,
    "code": CodeNode,
}

KEYWORDS: List[str] = ["pass", "break", "continue", "return"]

TEMPLATE_BUILTIN_NAMES: List[str] = [
    "dict", "enumerate", "float", "int", "bool", "list", "long", "reversed",
    "set", "slice", "tuple", "xrange", "abs", "all", "any", "callable",
    "chr", "cmp", "divmod", "filter", "hex", "id", "isinstance", "iter",
    "len", "max", "min", "oct", "ord", "pow", "range", "round", "True",
    "False", "None", "__import__",
]

TEMPLATE_BUILTINS: Dict[str, Any] = {
    name: getattr(builtins, name)
    for name in TEMPLATE_BUILTIN_NAMES
    if hasattr(builtins, name)
}


class ForLoop:
    """Wrapper for an iterable in a 'for' statement to provide loop helpers.

    This class provides context variables like `loop.index`, `loop.parity`, etc.,
    within a template's for-loop.

    Attributes:
        index (int): The current 1-based iteration index.
        index0 (int): The current 0-based iteration index.
        revindex (int): The 1-based index from the end of the loop.
        revindex0 (int): The 0-based index from the end of the loop.
        first (bool): True if this is the first iteration.
        last (bool): True if this is the last iteration.
        odd (bool): True if the `index` is odd.
        even (bool): True if the `index` is even.
        parity (str): "odd" or "even".
        length (int): The total number of items in the sequence.
        parent (Optional[ForLoopContext]): The context of the parent loop, if nested.

    Examples:
        >>> loop = ForLoop()
        >>> for x in loop.setup(['a', 'b', 'c']):
        ...     print(loop.index, loop.revindex, loop.parity, x)
        1 3 odd a
        2 2 even b
        3 1 odd c
    """

    def __init__(self) -> None:
        """Initializes the ForLoop."""
        self._ctx: Optional["ForLoopContext"] = None

    def __getattr__(self, name: str) -> Any:
        """Delegates attribute access to the current context."""
        if self._ctx is None:
            raise AttributeError(name)
        else:
            return getattr(self._ctx, name)

    def setup(self, seq: Iterable[Any]) -> Iterator[Any]:
        """Sets up the loop context for a new iteration.

        Args:
            seq (Iterable[Any]): The sequence to iterate over.

        Returns:
            Iterator[Any]: An iterator that yields items from the sequence.
        """
        self._push()
        return self._ctx.setup(seq)

    def _push(self) -> None:
        """Pushes a new context onto the stack for nested loops."""
        self._ctx = ForLoopContext(self, self._ctx)

    def _pop(self) -> None:
        """Pops the current context off the stack."""
        self._ctx = self._ctx.parent


class ForLoopContext:
    """Stackable context for ForLoop to support nested loops."""

    def __init__(self, forloop: ForLoop, parent: Optional["ForLoopContext"]) -> None:
        """Initializes a new context.

        Args:
            forloop (ForLoop): The parent ForLoop object.
            parent (Optional[ForLoopContext]): The context of the outer loop.
        """
        self._forloop = forloop
        self.parent = parent
        self.length = 0
        self.index = 0

    def setup(self, seq: Iterable[Any]) -> Iterator[Any]:
        """Sets up the iterator and length for this context.

        Args:
            seq (Iterable[Any]): The sequence to iterate over.

        Yields:
            Items from the sequence.
        """
        try:
            self.length = len(seq)
        except TypeError:
            self.length = 0  # For generators

        self.index = 0
        for item in seq:
            self.index += 1
            yield item
        self._forloop._pop()

    @property
    def index0(self) -> int:
        return self.index - 1

    @property
    def first(self) -> bool:
        return self.index == 1

    @property
    def last(self) -> bool:
        return self.index == self.length

    @property
    def odd(self) -> bool:
        return self.index % 2 == 1

    @property
    def even(self) -> bool:
        return self.index % 2 == 0

    @property
    def parity(self) -> str:
        return "odd" if self.odd else "even"

    @property
    def revindex0(self) -> int:
        return self.length - self.index

    @property
    def revindex(self) -> int:
        return self.length - self.index + 1


class BaseTemplate:
    """Base class for a template."""

    def __init__(
        self,
        code: Any,
        filename: str,
        filter: Optional[Callable[[str], str]],
        globals: Dict[str, Any],
        builtins: Dict[str, Any],
    ) -> None:
        """Initializes a BaseTemplate.

        Args:
            code (Any): The compiled Python code object for the template.
            filename (str): The name of the template file.
            filter (Optional[Callable[[str], str]]): The escaping function.
            globals (Dict[str, Any]): A dictionary of global variables.
            builtins (Dict[str, Any]): A dictionary of allowed built-in functions.
        """
        self.filename = filename
        self.filter = filter
        self._globals = globals
        self._builtins = builtins
        if code:
            self.t = self._compile(code)
        else:
            self.t = lambda: ""

    def _compile(self, code: Any) -> Callable:
        """Executes the compiled code to define the template function.

        Args:
            code (Any): The compiled code object.

        Returns:
            Callable: The generated template function.
        """
        env = self.make_env(self._globals or {}, self._builtins)
        exec(code, env)
        return env["__template__"]

    def __call__(self, *a: Any, **kw: Any) -> "TemplateResult":
        """Executes the template with the given arguments.

        Args:
            *a: Positional arguments for the template.
            **kw: Keyword arguments for the template.

        Returns:
            TemplateResult: The result of the template execution.
        """
        __hidetraceback__ = True  # noqa: F841
        return self.t(*a, **kw)

    def make_env(
        self, globals: Dict[str, Any], builtins_: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Creates the execution environment for the template.

        Args:
            globals (Dict[str, Any]): User-provided globals.
            builtins_ (Dict[str, Any]): Allowed built-ins.

        Returns:
            Dict[str, Any]: The complete environment dictionary.
        """
        if sys.implementation.name == "pypy":
            overridden_builtins = builtins.__dict__.keys() - builtins_.keys()

            def f(name: str, *args: Any, **kwargs: Any) -> None:
                raise NameError(f"name '{name}' is not defined")

            for name in overridden_builtins:
                if name not in globals:
                    globals[name] = partial(f, name)

        return dict(
            globals,
            __builtins__=builtins_,
            ForLoop=ForLoop,
            TemplateResult=TemplateResult,
            escape_=self._escape,
            join_=self._join,
        )

    def _join(self, *items: Any) -> str:
        """Joins multiple items into a single string."""
        return "".join(items)

    def _escape(self, value: Any, escape: bool = False) -> str:
        """Escapes a value if required.

        Args:
            value (Any): The value to process.
            escape (bool): If True, apply the template's filter.

        Returns:
            str: The processed (and possibly escaped) string.
        """
        if value is None:
            value = ""
        value = safeunicode(value)
        if escape and self.filter:
            value = self.filter(value)
        return value


class Template(BaseTemplate):
    """Represents a template that is parsed from a string."""

    CONTENT_TYPES: Dict[str, str] = {
        ".html": "text/html; charset=utf-8",
        ".xhtml": "application/xhtml+xml; charset=utf-8",
        ".txt": "text/plain",
    }
    FILTERS: Dict[str, Callable[[str], str]] = {
        ".html": websafe,
        ".xhtml": websafe,
        ".xml": websafe,
    }
    globals: Dict[str, Any] = {}

    def __init__(
        self,
        text: str,
        filename: str = "<template>",
        filter: Optional[Callable[[str], str]] = None,
        globals: Optional[Dict[str, Any]] = None,
        builtins: Optional[Dict[str, Any]] = None,
        extensions: Optional[List[Any]] = None,
    ) -> None:
        """Initializes and compiles a template from a string.

        Args:
            text (str): The template source code.
            filename (str): The filename for error reporting and content-type detection.
            filter (Optional[Callable[[str], str]]): A custom escaping function.
            globals (Optional[Dict[str, Any]]): Globals available to the template.
            builtins (Optional[Dict[str, Any]]): Custom allowed built-ins.
            extensions (Optional[List[Any]]): Parser extensions.
        """
        self.extensions = extensions or []
        text = Template.normalize_text(text)
        code = self.compile_template(text, filename)

        _, ext = os.path.splitext(filename)
        filter = filter or self.FILTERS.get(ext)
        self.content_type = self.CONTENT_TYPES.get(ext)

        globals = globals if globals is not None else self.globals
        builtins = builtins if builtins is not None else TEMPLATE_BUILTINS

        super().__init__(
            code=code,
            filename=filename,
            filter=filter,
            globals=globals,
            builtins=builtins,
        )

    def __repr__(self) -> str:
        """Returns a string representation of the template.

        Examples:
            >>> Template(text='Template text', filename='chart.html')
            <Template chart.html>
        """
        return f"<{self.__class__.__name__} {self.filename}>"

    @staticmethod
    def normalize_text(text: str) -> str:
        """Normalizes template text by fixing line endings and removing BOM.

        Args:
            text (str): The raw template text.

        Returns:
            str: The normalized template text.
        """
        text = text.replace("\r\n", "\n").replace("\r", "\n").expandtabs()
        if not text.endswith("\n"):
            text += "\n"

        BOM = "\xef\xbb\xbf"
        if isinstance(text, str) and text.startswith(BOM):
            text = text[len(BOM) :]

        text = text.replace(r"\$", "$$")
        return text

    def __call__(self, *a: Any, **kw: Any) -> "TemplateResult":
        """Executes the template and sets the Content-Type header if applicable."""
        __hidetraceback__ = True  # noqa: F841
        from . import webapi as web

        if "headers" in web.ctx and self.content_type:
            web.header("Content-Type", self.content_type, unique=True)

        return super().__call__(*a, **kw)

    @staticmethod
    def generate_code(
        text: str, filename: str, parser: Optional[Parser] = None
    ) -> str:
        """Generates Python code from a template string.

        Args:
            text (str): The template source string.
            filename (str): The filename for error reporting.
            parser (Optional[Parser]): A parser instance to use.

        Returns:
            str: The generated Python code as a string.
        """
        parser = parser or Parser()
        rootnode = parser.parse(text, filename)
        code = rootnode.emit(indent="").strip()
        return safestr(code)

    def create_parser(self) -> Parser:
        """Creates a parser instance, applying any configured extensions.

        Returns:
            Parser: The configured parser instance.
        """
        p = Parser()
        for ext in self.extensions:
            p = ext(p)
        return p

    def compile_template(self, template_string: str, filename: str) -> Any:
        """Compiles a template string into a Python code object.

        Args:
            template_string (str): The template source code.
            filename (str): The filename for compilation and error reporting.

        Returns:
            Any: The compiled code object.

        Raises:
            SyntaxError: If the generated Python code is invalid.
            SecurityError: If the template contains unsafe code.
        """
        code = Template.generate_code(
            template_string, filename, parser=self.create_parser()
        )

        def get_source_line(filename: str, lineno: int) -> Optional[str]:
            try:
                with open(filename, "r", encoding="utf-8") as f:
                    lines = f.read().splitlines()
                return lines[lineno]
            except (IOError, IndexError):
                return None

        try:
            compiled_code = compile(code, filename, "exec")
        except SyntaxError as err:
            msg = f"\n\nTemplate traceback:\n    File {repr(err.filename)}, line {err.lineno}\n        {get_source_line(err.filename, err.lineno - 1)}"
            err.msg += msg
            logging.error("Template Syntax Error: %s", err.msg, exc_info=True)
            raise

        ast_node = ast.parse(code, filename)
        SafeVisitor().walk(ast_node, filename)

        return compiled_code


class CompiledTemplate(Template):
    """A template that is loaded from a pre-compiled Python module."""

    def __init__(self, f: Callable, filename: str) -> None:
        """Initializes a CompiledTemplate.

        Args:
            f (Callable): The pre-compiled template function.
            filename (str): The original filename of the template.
        """
        super().__init__("", filename)
        self.t = f

    def compile_template(self, *a: Any) -> None:
        """Overrides base method; no compilation needed."""
        return None

    def _compile(self, *a: Any) -> None:
        """Overrides base method; no compilation needed."""
        return None


class Render:
    """A factory for loading and rendering templates from a directory.

    This is the standard way to use templates. An instance of this class
    points to a template directory, and templates can be accessed as attributes.

    Args:
        loc (str): The path to the template directory. Defaults to "templates".
        cache (Optional[bool]): Whether to cache templates in memory. Defaults
            to True if `web.config.debug` is False.
        base (Optional[Union[str, Callable]]): A base template to wrap around
            all rendered templates. Can be a template name or a callable.
        **keywords: Other keywords to pass to the `Template` constructor,
            such as `globals`.

    Examples:
        >>> # Assuming a file 'templates/index.html' exists:
        >>> # render = web.template.render('templates')
        >>> # print(render.index(name='World'))

        >>> # Using a base layout template:
        >>> # render = web.template.render('templates', base='layout')
        >>> # print(render.index())
    """

    def __init__(
        self,
        loc: str = "templates",
        cache: Optional[bool] = None,
        base: Optional[Union[str, Callable]] = None,
        **keywords: Any,
    ) -> None:
        """Initializes the Render object."""
        self._loc = loc
        self._keywords = keywords
        self._cache: Optional[Dict[str, Any]] = {} if cache else None
        if cache is None:
            self._cache = {} if not config.get("debug", False) else None

        if base and not hasattr(base, "__call__"):
            self._base: Optional[Callable] = lambda page: self._template(base)(page)
        else:
            self._base = base

    def _add_global(self, obj: Any, name: Optional[str] = None) -> None:
        """Adds a global variable to this rendering instance.

        Args:
            obj (Any): The object to add as a global.
            name (Optional[str]): The name for the global. Defaults to `obj.__name__`.
        """
        if "globals" not in self._keywords:
            self._keywords["globals"] = {}
        if not name:
            name = obj.__name__
        self._keywords["globals"][name] = obj

    def _lookup(self, name: str) -> Tuple[str, Optional[str]]:
        """Finds a template or subdirectory by name.

        Args:
            name (str): The name of the template or subdirectory.

        Returns:
            Tuple[str, Optional[str]]: A tuple of ('dir'|'file'|'none', path).
        """
        path = os.path.join(self._loc, name)
        if os.path.isdir(path):
            return "dir", path
        else:
            filepath = self._findfile(path)
            return ("file", filepath) if filepath else ("none", None)

    def _load_template(self, name: str) -> Union["Render", Template]:
        """Loads a template by name.

        Args:
            name (str): The name of the template.

        Returns:
            Union[Render, Template]: A new Render instance for a subdirectory,
            or a Template instance for a file.

        Raises:
            AttributeError: If the template is not found.
        """
        kind, path = self._lookup(name)

        if kind == "dir":
            return Render(
                path, cache=self._cache is not None, base=self._base, **self._keywords
            )
        elif kind == "file":
            with open(path, "r", encoding="utf-8") as tmpl_file:
                return Template(tmpl_file.read(), filename=path, **self._keywords)
        else:
            raise AttributeError(f"No template named {name}")

    def _findfile(self, path_prefix: str) -> Optional[str]:
        """Finds a template file given a prefix, trying various extensions.

        Args:
            path_prefix (str): The path to the template without an extension.

        Returns:
            Optional[str]: The full path to the found file, or None.
        """
        paths = [f for f in glob.glob(path_prefix + ".*") if not f.endswith("~")]
        paths.sort()

        if not paths and os.path.exists(path_prefix):
            paths = [path_prefix]

        return paths[0] if paths else None

    def _template(self, name: str) -> Union["Render", Template]:
        """Retrieves a template, using the cache if enabled.

        Args:
            name (str): The name of the template.

        Returns:
            Union[Render, Template]: The requested template or Render instance.
        """
        if self._cache is not None:
            if name not in self._cache:
                self._cache[name] = self._load_template(name)
            return self._cache[name]
        else:
            return self._load_template(name)

    def __getattr__(self, name: str) -> Union["Render", Callable]:
        """Magic method to access templates as attributes.

        Args:
            name (str): The name of the template.

        Returns:
            Union[Render, Callable]: The template object or a callable that
            wraps it with the base template.
        """
        t = self._template(name)
        if self._base and isinstance(t, Template):

            def template(*a: Any, **kw: Any) -> "TemplateResult":
                return self._base(t(*a, **kw))

            return template
        else:
            return t


class GAE_Render(Render):
    """A Render subclass for Google App Engine pre-compiled templates."""

    super = Render

    def __init__(self, loc: Any, *a: Any, **kw: Any) -> None:
        """Initializes the GAE_Render.

        Args:
            loc (Any): A module or a string path to a module.
            *a: Positional arguments for Render.
            **kw: Keyword arguments for Render.
        """
        super().__init__(loc, *a, **kw)

        if isinstance(loc, type(sys)):  # ModuleType
            self.mod = loc
        else:
            name = loc.rstrip("/").replace("/", ".")
            self.mod = __import__(name, None, None, ["x"])

        self.mod.__dict__.update(kw.get("builtins", TEMPLATE_BUILTINS))
        self.mod.__dict__.update(Template.globals)
        self.mod.__dict__.update(kw.get("globals", {}))

    def _load_template(self, name: str) -> Union["GAE_Render", Template]:
        """Loads a template from the pre-compiled module.

        Args:
            name (str): The name of the template function/submodule.

        Returns:
            Union[GAE_Render, Template]: The loaded template or a new renderer.
        """
        t = getattr(self.mod, name)
        if isinstance(t, type(sys)):
            return GAE_Render(
                t, cache=self._cache is not None, base=self._base, **self._keywords
            )
        else:
            return t


render = Render
try:
    from google import appengine  # noqa: F401

    render = Render = GAE_Render
except ImportError:
    pass


def frender(path: str, **keywords: Any) -> Template:
    """Creates a single template instance from a file path.

    Args:
        path (str): The path to the template file.
        **keywords: Keyword arguments to pass to the `Template` constructor.

    Returns:
        Template: The initialized Template object.
    """
    with open(path, "r", encoding="utf-8") as f:
        return Template(f.read(), filename=path, **keywords)


def compile_templates(root: str) -> None:
    """Compiles a directory of templates into Python modules.

    This function walks a directory tree and converts all template files
    into a `__init__.py` in each directory, containing the compiled Python
    code for the templates.

    Args:
        root (str): The root directory of the templates to compile.
    """
    for dirpath, dirnames, filenames in os.walk(root):
        filenames = [
            f
            for f in filenames
            if not f.startswith(".")
            and not f.endswith("~")
            and not f.startswith("__init__.py")
        ]

        for d in dirnames[:]:
            if d.startswith("."):
                dirnames.remove(d)

        init_py_path = os.path.join(dirpath, "__init__.py")
        with open(init_py_path, "w", encoding="utf-8") as out:
            out.write(
                "from web.template import CompiledTemplate, ForLoop, TemplateResult\n\n"
            )
            if dirnames:
                out.write("import " + ", ".join(dirnames))
            out.write("\n")

            for f in filenames:
                path = os.path.join(dirpath, f)
                name, _ = os.path.splitext(f)

                with open(path, "r", encoding="utf-8") as tmpl_file:
                    text = tmpl_file.read()
                text = Template.normalize_text(text)
                code = Template.generate_code(text, path)
                code = code.replace("__template__", name, 1)

                out.write(code)
                out.write("\n\n")
                out.write(f"{name} = CompiledTemplate({name}, {repr(path)})\n")
                out.write(f"join_ = {name}._join; escape_ = {name}._escape\n\n")

                # Validate compilation
                with open(path, "r", encoding="utf-8") as tmpl_file:
                    Template(tmpl_file.read(), path)


class ParseError(Exception):
    """Exception raised for errors during template parsing."""

    pass


class SecurityError(Exception):
    """Exception raised when a template contains potentially unsafe code."""

    pass


ALLOWED_AST_NODES: List[str] = [
    "Add", "And", "Assign", "Attribute", "AugAssign", "AugLoad", "AugStore",
    "BinOp", "BitAnd", "BitOr", "BitXor", "BoolOp", "Break", "Call",
    "ClassDef", "Compare", "Constant", "Continue", "Del", "Delete", "Dict",
    "DictComp", "Div", "Ellipsis", "Eq", "ExceptHandler", "Expr",
    "Expression", "ExtSlice", "FloorDiv", "For", "FunctionDef",
    "GeneratorExp", "Gt", "GtE", "If", "IfExp", "In", "Index",
    "Interactive", "Invert", "Is", "IsNot", "JoinedStr", "LShift", "Lambda",
    "List", "ListComp", "Load", "Lt", "LtE", "Mod", "Module", "Mult",
    "Name", "NameConstant", "Not", "NotEq", "NotIn", "Num", "Or", "Param",
    "Pass", "Pow", "RShift", "Return", "Set", "SetComp", "Slice", "Store",
    "Str", "Sub", "Subscript", "Suite", "Tuple", "UAdd", "USub", "UnaryOp",
    "While", "With", "Yield", "alias", "arg", "arguments", "comprehension",
    "keyword",
]


class SafeVisitor(ast.NodeVisitor):
    """An `ast.NodeVisitor` that validates the safety of generated template code.

    This visitor walks the Abstract Syntax Tree of the generated Python code
    and raises a `SecurityError` if it finds disallowed constructs, such as
    `import`, `exec`, or access to private attributes (starting with '_').
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initializes the visitor."""
        super().__init__(*args, **kwargs)
        self.errors: List[SecurityError] = []
        self.filename: str = ""

    def walk(self, tree: ast.AST, filename: str) -> None:
        """Walks the AST and raises SecurityError if unsafe code is found.

        Args:
            tree (ast.AST): The root of the AST to validate.
            filename (str): The filename for error reporting.

        Raises:
            SecurityError: If any unsafe constructs are found.
        """
        self.filename = filename
        self.visit(tree)
        if self.errors:
            raise SecurityError("\n".join([str(err) for err in self.errors]))

    def generic_visit(self, node: ast.AST) -> None:
        """Visits a node, checking if its type is in the allowed list."""
        nodename = type(node).__name__
        if nodename not in ALLOWED_AST_NODES:
            self.fail_node(node, nodename)
        super().generic_visit(node)

    def visit_Name(self, node: ast.Name) -> None:
        """Checks for access to names starting with '__'."""
        if node.id.startswith("__"):
            self.fail_name(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        """Checks for access to disallowed attributes."""
        attrname = self.get_node_attr(node)
        if self.is_unallowed_attr(attrname):
            self.fail_attribute(node, attrname)
        super().generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> None:
        """Checks assignment targets for safety."""
        self.check_assign_targets(node)

    def visit_AugAssign(self, node: ast.AugAssign) -> None:
        """Checks augmented assignment target for safety."""
        self.check_assign_target(node)

    def check_assign_targets(self, node: ast.Assign) -> None:
        """Iterates through assignment targets and checks each one."""
        for target in node.targets:
            self.check_assign_target(target)
        super().generic_visit(node)

    def check_assign_target(self, targetnode: ast.AST) -> None:
        """Checks if an assignment target is a disallowed attribute."""
        if isinstance(targetnode, ast.Attribute):
            attrname = self.get_node_attr(targetnode)
            self.fail_attribute(targetnode, attrname)

    def fail_node(self, node: ast.AST, nodename: str) -> None:
        """Records a security error for a disallowed node type."""
        lineno = self.get_node_lineno(node)
        e = SecurityError(
            f"{self.filename}:{lineno} - execution of '{nodename}' "
            "statements is denied"
        )
        self.errors.append(e)

    def fail_attribute(self, node: ast.AST, attrname: str) -> None:
        """Records a security error for disallowed attribute access."""
        lineno = self.get_node_lineno(node)
        e = SecurityError(
            f"{self.filename}:{lineno} - access to attribute '{attrname}' is denied"
        )
        self.errors.append(e)

    def fail_name(self, node: ast.Name) -> None:
        """Records a security error for disallowed name access."""
        lineno = self.get_node_lineno(node)
        e = SecurityError(
            f"{self.filename}:{lineno} - access to name '{node.id}' is denied"
        )
        self.errors.append(e)

    def is_unallowed_attr(self, name: Optional[str]) -> bool:
        """Checks if an attribute name is disallowed."""
        return bool(
            name
            and (
                name.startswith("_")
                or name.startswith("func_")
                or name.startswith("im_")
            )
        )

    def get_node_attr(self, node: ast.AST) -> Optional[str]:
        """Safely gets the 'attr' attribute from an AST node."""
        return getattr(node, "attr", None)

    def get_node_lineno(self, node: ast.AST) -> int:
        """Safely gets the line number from an AST node."""
        return getattr(node, "lineno", 0)


class TemplateResult(MutableMapping):
    """A dictionary-like object for storing template output and variables.

    The result of a template execution is stored in this object. The main
    string output is accumulated and can be accessed as a string representation
    of the object itself. Variables set with `$var` are stored as attributes.

    Attributes:
        __body__ (str): The rendered string output of the template.

    Examples:
        >>> d = TemplateResult(__body__='hello, world', x='foo')
        >>> str(d)
        'hello, world'
        >>> d.x
        'foo'
        >>> d = TemplateResult()
        >>> d.extend(['hello', 'world'])
        >>> str(d)
        'helloworld'
    """

    def __init__(self, *a: Any, **kw: Any) -> None:
        """Initializes the TemplateResult."""
        self.__dict__["_d"] = dict(*a, **kw)
        self.__dict__["_parts"]: List[str] = []
        self.__dict__["extend"] = self._parts.extend
        self._d.setdefault("__body__", None)

    def keys(self) -> list:
        """Returns the keys of the underlying dictionary."""
        return list(self._d.keys())

    def _prepare_body(self) -> None:
        """Joins the collected parts to form the final `__body__` string."""
        if self._parts:
            value = "".join(self._parts)
            self._parts[:] = []
            body = self._d.get("__body__")
            self._d["__body__"] = (body + value) if body else value

    def __getitem__(self, name: str) -> Any:
        """Gets an item, preparing the body if requested."""
        if name == "__body__":
            self._prepare_body()
        return self._d[name]

    def __setitem__(self, name: str, value: Any) -> None:
        """Sets an item, preparing the body if it's being set."""
        if name == "__body__":
            self._prepare_body()
        self._d[name] = value

    def __delitem__(self, name: str) -> None:
        """Deletes an item, preparing the body if it's being deleted."""
        if name == "__body__":
            self._prepare_body()
        del self._d[name]

    def __getattr__(self, key: str) -> Any:
        """Gets an item as an attribute."""
        try:
            return self[key]
        except KeyError as k:
            raise AttributeError(k) from k

    def __setattr__(self, key: str, value: Any) -> None:
        """Sets an item as an attribute."""
        self[key] = value

    def __delattr__(self, key: str) -> None:
        """Deletes an item as an attribute."""
        try:
            del self[key]
        except KeyError as k:
            raise AttributeError(k) from k

    def __str__(self) -> str:
        """Returns the rendered body as a string."""
        self._prepare_body()
        return str(self["__body__"] or "")

    def __repr__(self) -> str:
        """Returns a string representation of the object."""
        self._prepare_body()
        return f"<TemplateResult: {self._d}>"

    def __len__(self) -> int:
        """Returns the number of items (including `__body__`)."""
        return len(self._d)

    def __iter__(self) -> Iterator[str]:
        """Iterates over the keys."""
        for i in self._d.__iter__():
            if i == "__body__":
                self._prepare_body()
            yield i


def test() -> None:
    """Doctests for the template module.

    Examples:
        >>> class TestResult:
        ...     def __init__(self, t): self.t = t
        ...     def __getattr__(self, name): return getattr(self.t, name)
        ...     def __repr__(self): return str(self.t)
        ...
        >>> def t(code, **keywords):
        ...     tmpl = Template(code, **keywords)
        ...     return lambda *a, **kw: TestResult(tmpl(*a, **kw))
        ...
        >>> t('$def with (a)\n$a')(1)
        u'1\\n'
        >>> t('$if 1: 1')()
        u'1\\n'
        >>> t('$for x in [1, 2, 3]: $x')()
        u'1\\n2\\n3\\n'
        >>> t('$ a = 1\\n$a')()
        u'1\\n'
        >>> t("Stop, $$money isn't evaluated.")()
        u"Stop, $money isn't evaluated.\\n"
        >>> import datetime
        >>> t("$def with (d)\\n$d.strftime('%Y')")(datetime.date(2023, 1, 1))
        u'2023\\n'
    """
    pass


if __name__ == "__main__":
    if "--compile" in sys.argv:
        compile_templates(sys.argv[2])
    else:
        import doctest

        doctest.testmod()