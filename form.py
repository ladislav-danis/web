"""
HTML forms
(part of web.py)

This module provides classes for creating and handling HTML forms.

Example:
    >>> from web.form import Form, Textbox
    >>> f = Form(Textbox("username"))
    >>> print(f.render())
    <table>
        <tr><th><label for="username">username</label></th><td><input id="username" name="username" type="text"/></td></tr>
    </table>
"""

import copy
import re

from . import net, utils
from . import webapi as web


def attrget(obj, attr, value=None):
    """
    Get attribute from object with fallback.

    Args:
        obj: The object to get the attribute from.
        attr: The name of the attribute to get.
        value: Default value if attribute is not found.

    Returns:
        The value of the attribute or the default value.

    Examples:
        >>> class TestObj:
        ...     def __init__(self):
        ...         self.test_attr = 'test_value'
        >>> obj = TestObj()
        >>> attrget(obj, 'test_attr')
        'test_value'
        >>> attrget(obj, 'nonexistent', 'default')
        'default'
    """
    try:
        if hasattr(obj, "has_key") and attr in obj:
            return obj[attr]
    except TypeError:
        # Handle the case where has_key takes different number of arguments.
        # This is the case with Model objects on appengine. See #134
        pass
    if (
        hasattr(obj, "keys") and attr in obj
    ):  # needed for Py3, has_key doesn't exist anymore
        return obj[attr]
    elif hasattr(obj, attr):
        return getattr(obj, attr)
    return value


class Form:
    """
    HTML form.

    Args:
        *inputs: Input fields to include in the form.
        **kw: Additional keyword arguments including validators.

    Examples:
        >>> from web.form import Form, Textbox
        >>> f = Form(Textbox("x"))
        >>> f.render()
        u'<table>\\n    <tr><th><label for="x">x</label></th><td><input id="x" name="x" type="text"/></td></tr>\\n</table>'
        >>> f.fill(x="42")
        True
        >>> f.render()
        u'<table>\\n    <tr><th><label for="x">x</label></th><td><input id="x" name="x" type="text" value="42"/></td></tr>\\n</table>'
    """

    def __init__(self, *inputs, **kw):
        """
        Initialize a Form instance.

        Args:
            *inputs: Input fields to include in the form.
            **kw: Additional keyword arguments including validators.
        """
        self.inputs = inputs
        self.valid = True
        self.note = None
        self.validators = kw.pop("validators", [])

    def __call__(self, x=None):
        """
        Call the form with validation.

        Args:
            x: Data to validate against the form.

        Returns:
            A copy of the form with validation results.
        """
        o = copy.deepcopy(self)
        if x:
            o.validates(x)
        return o

    def render(self):
        """
        Render the HTML form.

        Returns:
            String containing the rendered HTML form.
        """
        out = ""
        out += self.rendernote(self.note)
        out += "<table>\n"

        for i in self.inputs:
            html = (
                utils.safeunicode(i.pre)
                + i.render()
                + self.rendernote(i.note)
                + utils.safeunicode(i.post)
            )
            if i.is_hidden():
                out += '    <tr style="display: none;"><th></th><td>%s</td></tr>\n' % (
                    html
                )
            else:
                out += f'    <tr><th><label for="{net.websafe(i.id)}">{net.websafe(i.description)}</label></th><td>{html}</td></tr>\n'
        out += "</table>"
        return out

    def render_css(self):
        """
        Render the form in CSS format.

        Returns:
            String containing the rendered HTML form with CSS styling.
        """
        out = []
        out.append(self.rendernote(self.note))
        for i in self.inputs:
            if not i.is_hidden():
                out.append(
                    f'<label for="{net.websafe(i.id)}">{net.websafe(i.description)}</label>'
                )
            out.append(i.pre)
            out.append(i.render())
            out.append(self.rendernote(i.note))
            out.append(i.post)
            out.append("\n")
        return "".join(out)

    def rendernote(self, note):
        """
        Render a note for the form.

        Args:
            note: The note to render.

        Returns:
            String containing the rendered note.
        """
        if note:
            return '<strong class="wrong">%s</strong>' % net.websafe(note)
        else:
            return ""

    def validates(self, source=None, _validate=True, **kw):
        """
        Validate form data.

        Args:
            source: Source of form data (dict or web.input).
            _validate: Whether to perform validation.
            **kw: Additional keyword arguments for form data.

        Returns:
            Boolean indicating whether validation passed.
        """
        source = source or kw or web.input()
        out = True
        for i in self.inputs:
            v = attrget(source, i.name)
            if _validate:
                if not i.validate(v):
                    self.note = i.note
                    return False
            else:
                i.set_value(v)
        if _validate:
            out = out and self._validate(source)
            self.valid = out
        return out

    def _validate(self, value):
        """
        Internal validation method.

        Args:
            value: Value to validate.

        Returns:
            Boolean indicating whether validation passed.
        """
        self.value = value
        for v in self.validators:
            if not v.valid(value):
                self.note = v.msg
                return False
        return True

    def fill(self, source=None, **kw):
        """
        Fill form with data without validation.

        Args:
            source: Source of form data (dict or web.input).
            **kw: Additional keyword arguments for form data.

        Returns:
            Boolean indicating whether filling was successful.
        """
        return self.validates(source, _validate=False, **kw)

    def __getitem__(self, i):
        """
        Get input field by name.

        Args:
            i: Name of the input field.

        Returns:
            The input field with the specified name.

        Raises:
            KeyError: If no input field with that name exists.
        """
        for x in self.inputs:
            if x.name == i:
                return x
        raise KeyError(i)

    def __getattr__(self, name):
        """
        Get input field by attribute access.

        Args:
            name: Name of the input field.

        Returns:
            The input field with the specified name.

        Raises:
            AttributeError: If no input field with that name exists.
        """
        # don't interfere with deepcopy
        inputs = self.__dict__.get("inputs") or []
        for x in inputs:
            if x.name == name:
                return x
        raise AttributeError(name)

    def get(self, i, default=None):
        """
        Get input field by name with default fallback.

        Args:
            i: Name of the input field.
            default: Default value to return if field not found.

        Returns:
            The input field or default value.
        """
        try:
            return self[i]
        except KeyError:
            return default

    def _get_d(self):  # @@ should really be form.attr, no?
        """
        Get form data as storage object.

        Returns:
            Storage object containing form data.
        """
        return utils.storage([(i.name, i.get_value()) for i in self.inputs])

    d = property(_get_d)


class Input:
    """
    Generic input. Type attribute must be specified when called directly.

    See also: <https://www.w3.org/TR/html52/sec-forms.html#the-input-element>

    Currently only types which can be written inside one `<input />` tag are
    supported.

    - For checkbox, please use `Checkbox` class for better control.
    - For radiobox, please use `Radio` class for better control.

    Args:
        name: Name of the input field.
        *validators: Validators to apply to the input.
        **attrs: Additional HTML attributes for the input.

    Examples:
        >>> from web.form import Input
        >>> Input(name='foo', type='email', value="user@domain.com").render()
        u'<input id="foo" name="foo" type="email" value="user@domain.com"/>'
        >>> Input(name='foo', type='number', value="bar").render()
        u'<input id="foo" name="foo" type="number" value="bar"/>'
        >>> Input(name='num', type="number", min='0', max='10', step='2', value='5').render()
        u'<input id="num" max="10" min="0" name="num" step="2" type="number" value="5"/>'
        >>> Input(name='foo', type="tel", value='55512345').render()
        u'<input id="foo" name="foo" type="tel" value="55512345"/>'
        >>> Input(name='search', type="search", value='Search').render()
        u'<input id="search" name="search" type="search" value="Search"/>'
        >>> Input(name='search', type="search", value='Search', required='required', pattern='[a-z0-9]{2,30}', placeholder='Search...').render()
        u'<input id="search" name="search" pattern="[a-z0-9]{2,30}" placeholder="Search..." required="required" type="search" value="Search"/>'
        >>> Input(name='url', type="url", value='url').render()
        u'<input id="url" name="url" type="url" value="url"/>'
        >>> Input(name='range', type="range", min='0', max='10', step='2', value='5').render()
        u'<input id="range" max="10" min="0" name="range" step="2" type="range" value="5"/>'
        >>> Input(name='color', type="color").render()
        u'<input id="color" name="color" type="color"/>'
        >>> Input(name='f', type="file", accept=".doc,.docx,.xml").render()
        u'<input accept=".doc,.docx,.xml" id="f" name="f" type="file"/>'
    """

    def __init__(self, name, *validators, **attrs):
        """
        Initialize an Input instance.

        Args:
            name: Name of the input field.
            *validators: Validators to apply to the input.
            **attrs: Additional HTML attributes for the input.
        """
        self.name = name
        self.validators = validators
        self.attrs = attrs = AttributeList(attrs)

        self.type = attrs.pop("type", None)
        self.description = attrs.pop("description", name)
        self.value = attrs.pop("value", None)
        self.pre = attrs.pop("pre", "")
        self.post = attrs.pop("post", "")
        self.note = None

        self.id = attrs.setdefault("id", self.get_default_id())

        if "class_" in attrs:
            attrs["class"] = attrs["class_"]
            del attrs["class_"]

    def is_hidden(self):
        """
        Check if input is hidden.

        Returns:
            Boolean indicating whether the input is hidden.
        """
        return False

    def get_type(self):
        """
        Get the type of the input.

        Returns:
            String representing the input type.

        Raises:
            AttributeError: If no type attribute is specified.
        """
        if self.type is not None:
            return self.type
        else:
            raise AttributeError("missing attribute 'type'")

    def get_default_id(self):
        """
        Get default ID for the input.

        Returns:
            String representing the default ID.
        """
        return self.name

    def validate(self, value):
        """
        Validate the input value.

        Args:
            value: Value to validate.

        Returns:
            Boolean indicating whether validation passed.
        """
        self.set_value(value)

        for v in self.validators:
            if not v.valid(value):
                self.note = v.msg
                return False
        return True

    def set_value(self, value):
        """
        Set the input value.

        Args:
            value: Value to set.
        """
        self.value = value

    def get_value(self):
        """
        Get the current input value.

        Returns:
            The current value of the input.
        """
        return self.value

    def render(self):
        """
        Render the HTML input element.

        Returns:
            String containing the rendered HTML input element.
        """
        attrs = self.attrs.copy()
        attrs["type"] = self.get_type()
        if self.value is not None:
            attrs["value"] = self.value
        attrs["name"] = self.name
        attrs["id"] = self.id
        return "<input %s/>" % attrs

    def rendernote(self, note):
        """
        Render a note for the input.

        Args:
            note: The note to render.

        Returns:
            String containing the rendered note.
        """
        if note:
            return '<strong class="wrong">%s</strong>' % net.websafe(note)
        else:
            return ""

    def addatts(self):
        """
        Add attributes to input (backward compatibility).

        Returns:
            String with space-prefixed attributes.
        """
        # add leading space for backward-compatibility
        return " " + str(self.attrs)


class AttributeList(dict):
    """
    List of attributes of input.

    Args:
        **attrs: Dictionary of attributes.

    Examples:
        >>> from web.form import AttributeList
        >>> a = AttributeList(type='text', name='x', value=20)
        >>> a
        <attrs: 'name="x" type="text" value="20"'>
    """

    def copy(self):
        """
        Create a copy of the attribute list.

        Returns:
            A new AttributeList instance with copied attributes.
        """
        return AttributeList(self)

    def __str__(self):
        """
        Convert attributes to string representation.

        Returns:
            String containing all attributes in HTML format.
        """
        return " ".join([f'{k}="{net.websafe(v)}"' for k, v in sorted(self.items())])

    def __repr__(self):
        """
        Get string representation of the attribute list.

        Returns:
            String representation of the attribute list.
        """
        return "<attrs: %s>" % repr(str(self))


class Textbox(Input):
    """
    Textbox input.

    Examples:
        >>> from web.form import Textbox
        >>> Textbox(name='foo', value='bar').render()
        u'<input id="foo" name="foo" type="text" value="bar"/>'
        >>> Textbox(name='foo', value=0).render()
        u'<input id="foo" name="foo" type="text" value="0"/>'
    """

    def get_type(self):
        """
        Get the type of the input.

        Returns:
            String 'text'.
        """
        return "text"


class Password(Input):
    """
    Password input.

    Examples:
        >>> from web.form import Password
        >>> Password(name='password', value='secret').render()
        u'<input id="password" name="password" type="password" value="secret"/>'
    """

    def get_type(self):
        """
        Get the type of the input.

        Returns:
            String 'password'.
        """
        return "password"


class Textarea(Input):
    """
    Textarea input.

    Examples:
        >>> from web.form import Textarea
        >>> Textarea(name='foo', value='bar').render()
        u'<textarea id="foo" name="foo">bar</textarea>'
    """

    def render(self):
        """
        Render the HTML textarea element.

        Returns:
            String containing the rendered HTML textarea element.
        """
        attrs = self.attrs.copy()
        attrs["name"] = self.name
        value = net.websafe(self.value or "")
        return f"<textarea {attrs}>{value}</textarea>"


class Dropdown(Input):
    """
    Dropdown/select input.

    Args:
        name: Name of the dropdown.
        args: List of options for the dropdown.
        *validators: Validators to apply to the input.
        **attrs: Additional HTML attributes for the input.

    Examples:
        >>> from web.form import Dropdown
        >>> Dropdown(name='foo', args=['a', 'b', 'c'], value='b').render()
        u'<select id="foo" name="foo">\\n  <option value="a">a</option>\\n  <option selected="selected" value="b">b</option>\\n  <option value="c">c</option>\\n</select>\\n'
        >>> Dropdown(name='foo', args=[('a', 'aa'), ('b', 'bb'), ('c', 'cc')], value='b').render()
        u'<select id="foo" name="foo">\\n  <option value="a">aa</option>\\n  <option selected="selected" value="b">bb</option>\\n  <option value="c">cc</option>\\n</select>\\n'
    """

    def __init__(self, name, args, *validators, **attrs):
        """
        Initialize a Dropdown instance.

        Args:
            name: Name of the dropdown.
            args: List of options for the dropdown.
            *validators: Validators to apply to the input.
            **attrs: Additional HTML attributes for the input.
        """
        self.args = args
        super().__init__(name, *validators, **attrs)

    def render(self):
        """
        Render the HTML select element.

        Returns:
            String containing the rendered HTML select element.
        """
        attrs = self.attrs.copy()
        attrs["name"] = self.name

        x = "<select %s>\n" % attrs

        for arg in self.args:
            x += self._render_option(arg)

        x += "</select>\n"
        return x

    def _render_option(self, arg, indent="  "):
        """
        Render a single option element.

        Args:
            arg: Option argument (value or tuple of value and description).
            indent: Indentation for the option element.

        Returns:
            String containing the rendered HTML option element.
        """
        if isinstance(arg, (tuple, list)):
            value, desc = arg
        else:
            value, desc = arg, arg

        value = utils.safestr(value)
        if isinstance(self.value, (tuple, list)):
            s_value = [utils.safestr(x) for x in self.value]
        else:
            s_value = utils.safestr(self.value)

        if s_value == value or (isinstance(s_value, list) and value in s_value):
            select_p = ' selected="selected"'
        else:
            select_p = ""
        return (
            indent
            + f'<option{select_p} value="{net.websafe(value)}">{net.websafe(desc)}</option>\n'
        )


class GroupedDropdown(Dropdown):
    """
    Grouped Dropdown/select input.

    Args:
        name: Name of the grouped dropdown.
        args: List of tuples containing label and options for the dropdown.
        *validators: Validators to apply to the input.
        **attrs: Additional HTML attributes for the input.

    Examples:
        >>> from web.form import GroupedDropdown
        >>> GroupedDropdown(name='car_type', args=(('Swedish Cars', ('Volvo', 'Saab')), ('German Cars', ('Mercedes', 'Audi'))), value='Audi').render()
        u'<select id="car_type" name="car_type">\\n  <optgroup label="Swedish Cars">\\n    <option value="Volvo">Volvo</option>\\n    <option value="Saab">Saab</option>\\n  </optgroup>\\n  <optgroup label="German Cars">\\n    <option value="Mercedes">Mercedes</option>\\n    <option selected="selected" value="Audi">Audi</option>\\n  </optgroup>\\n</select>\\n'
        >>> GroupedDropdown(name='car_type', args=(('Swedish Cars', (('v', 'Volvo'), ('s', 'Saab'))), ('German Cars', (('m', 'Mercedes'), ('a', 'Audi')))), value='a').render()
        u'<select id="car_type" name="car_type">\\n  <optgroup label="Swedish Cars">\\n    <option value="v">Volvo</option>\\n    <option value="s">Saab</option>\\n  </optgroup>\\n  <optgroup label="German Cars">\\n    <option value="m">Mercedes</option>\\n    <option selected="selected" value="a">Audi</option>\\n  </optgroup>\\n</select>\\n'
    """

    def __init__(self, name, args, *validators, **attrs):
        """
        Initialize a GroupedDropdown instance.

        Args:
            name: Name of the grouped dropdown.
            args: List of tuples containing label and options for the dropdown.
            *validators: Validators to apply to the input.
            **attrs: Additional HTML attributes for the input.
        """
        self.args = args
        super().__init__(name, *validators, **attrs)

    def render(self):
        """
        Render the HTML select element with grouped options.

        Returns:
            String containing the rendered HTML select element with grouped options.
        """
        attrs = self.attrs.copy()
        attrs["name"] = self.name

        x = "<select %s>\n" % attrs

        for label, options in self.args:
            x += '  <optgroup label="%s">\n' % net.websafe(label)
            for arg in options:
                x += self._render_option(arg, indent="    ")
            x += "  </optgroup>\n"

        x += "</select>\n"
        return x


class Radio(Input):
    """
    Radio input.

    Args:
        name: Name of the radio group.
        args: List of options for the radio buttons.
        *validators: Validators to apply to the input.
        **attrs: Additional HTML attributes for the input.
    """

    def __init__(self, name, args, *validators, **attrs):
        """
        Initialize a Radio instance.

        Args:
            name: Name of the radio group.
            args: List of options for the radio buttons.
            *validators: Validators to apply to the input.
            **attrs: Additional HTML attributes for the input.
        """
        self.args = args
        super().__init__(name, *validators, **attrs)

    def render(self):
        """
        Render the HTML radio button elements.

        Returns:
            String containing the rendered HTML radio button elements.
        """
        x = "<span>"
        for idx, arg in enumerate(self.args, start=1):
            if isinstance(arg, (tuple, list)):
                value, desc = arg
            else:
                value, desc = arg, arg
            attrs = self.attrs.copy()
            attrs["name"] = self.name
            attrs["type"] = "radio"
            attrs["value"] = value
            attrs["id"] = self.name + str(idx)
            if self.value == value:
                attrs["checked"] = "checked"
            x += f"<input {attrs}/> {net.websafe(desc)}"
        x += "</span>"
        return x


class Checkbox(Input):
    """
    Checkbox input.

    Examples:
        >>> from web.form import Checkbox
        >>> Checkbox('foo', value='bar', checked=True).render()
        u'<input checked="checked" id="foo_bar" name="foo" type="checkbox" value="bar"/>'
        >>> Checkbox('foo', value='bar').render()
        u'<input id="foo_bar" name="foo" type="checkbox" value="bar"/>'
        >>> c = Checkbox('foo', value='bar')
        >>> c.validate('on')
        True
        >>> c.render()
        u'<input checked="checked" id="foo_bar" name="foo" type="checkbox" value="bar"/>'
    """

    def __init__(self, name, *validators, **attrs):
        """
        Initialize a Checkbox instance.

        Args:
            name: Name of the checkbox.
            *validators: Validators to apply to the input.
            **attrs: Additional HTML attributes for the input.
        """
        self.checked = attrs.pop("checked", False)
        Input.__init__(self, name, *validators, **attrs)

    def get_default_id(self):
        """
        Get default ID for the checkbox.

        Returns:
            String representing the default ID.
        """
        value = utils.safestr(self.value or "")
        return self.name + "_" + value.replace(" ", "_")

    def render(self):
        """
        Render the HTML checkbox element.

        Returns:
            String containing the rendered HTML checkbox element.
        """
        attrs = self.attrs.copy()
        attrs["type"] = "checkbox"
        attrs["name"] = self.name
        attrs["value"] = self.value

        if self.checked:
            attrs["checked"] = "checked"
        return "<input %s/>" % attrs

    def set_value(self, value):
        """
        Set the checkbox value.

        Args:
            value: Value to set.
        """
        self.checked = bool(value)

    def get_value(self):
        """
        Get the current checkbox value.

        Returns:
            Boolean indicating whether the checkbox is checked.
        """
        return self.checked


class Button(Input):
    """
    HTML Button.

    Examples:
        >>> from web.form import Button
        >>> Button("save").render()
        u'<button id="save" name="save">save</button>'
        >>> Button("action", value="save", html="<b>Save Changes</b>").render()
        u'<button id="action" name="action" value="save"><b>Save Changes</b></button>'
    """

    def __init__(self, name, *validators, **attrs):
        """
        Initialize a Button instance.

        Args:
            name: Name of the button.
            *validators: Validators to apply to the input.
            **attrs: Additional HTML attributes for the input.
        """
        super().__init__(name, *validators, **attrs)
        self.description = ""

    def render(self):
        """
        Render the HTML button element.

        Returns:
            String containing the rendered HTML button element.
        """
        attrs = self.attrs.copy()
        attrs["name"] = self.name
        if self.value is not None:
            attrs["value"] = self.value
        html = attrs.pop("html", None) or net.websafe(self.name)
        return f"<button {attrs}>{html}</button>"


class Hidden(Input):
    """
    Hidden Input.

    Examples:
        >>> from web.form import Hidden
        >>> Hidden(name='foo', value='bar').render()
        u'<input id="foo" name="foo" type="hidden" value="bar"/>'
    """

    def is_hidden(self):
        """
        Check if input is hidden.

        Returns:
            Boolean indicating whether the input is hidden.
        """
        return True

    def get_type(self):
        """
        Get the type of the input.

        Returns:
            String 'hidden'.
        """
        return "hidden"


class File(Input):
    """
    File input.

    Examples:
        >>> from web.form import File
        >>> File(name='f', accept=".doc,.docx,.xml").render()
        u'<input accept=".doc,.docx,.xml" id="f" name="f" type="file"/>'
    """

    def get_type(self):
        """
        Get the type of the input.

        Returns:
            String 'file'.
        """
        return "file"


class Telephone(Input):
    """
    Telephone input.

    See: <https://html.spec.whatwg.org/#telephone-state-(type=tel)>

    Examples:
        >>> from web.form import Telephone
        >>> Telephone(name='tel', value='55512345').render()
        u'<input id="tel" name="tel" type="tel" value="55512345"/>'
    """

    def get_type(self):
        """
        Get the type of the input.

        Returns:
            String 'tel'.
        """
        return "tel"


class Email(Input):
    """
    Email input.

    See: <https://html.spec.whatwg.org/#e-mail-state-(type=email)>

    Examples:
        >>> from web.form import Email
        >>> Email(name='email', value='me@example.org').render()
        u'<input id="email" name="email" type="email" value="me@example.org"/>'
    """

    def get_type(self):
        """
        Get the type of the input.

        Returns:
            String 'email'.
        """
        return "email"


class Date(Input):
    """
    Date input.

    Note: Not supported by desktop Safari, Internet Explorer, or Opera Mini

    See: <https://html.spec.whatwg.org/#date-state-(type=date)>

    Examples:
        >>> from web.form import Date
        >>> Date(name='date', value='2020-04-01').render()
        u'<input id="date" name="date" type="date" value="2020-04-01"/>'
    """

    def get_type(self):
        """
        Get the type of the input.

        Returns:
            String 'date'.
        """
        return "date"


class Time(Input):
    """
    Time input.

    Note: Not supported by desktop Safari, Internet Explorer, or Opera Mini

    See: <https://html.spec.whatwg.org/#time-state-(type=time)>

    Examples:
        >>> from web.form import Time
        >>> Time(name='time', value='07:00').render()
        u'<input id="time" name="time" type="time" value="07:00"/>'
    """

    def get_type(self):
        """
        Get the type of the input.

        Returns:
            String 'time'.
        """
        return "time"


class Search(Input):
    """
    Search input.

    See: <https://html.spec.whatwg.org/#text-(type=text)-state-and-search-state-(type=search)>

    Examples:
        >>> from web.form import Search
        >>> Search(name='search', value='Search').render()
        u'<input id="search" name="search" type="search" value="Search"/>'
        >>> Search(name='search', value='Search', required='required', pattern='[a-z0-9]{2,30}', placeholder='Search...').render()
        u'<input id="search" name="search" pattern="[a-z0-9]{2,30}" placeholder="Search..." required="required" type="search" value="Search"/>'
    """

    def get_type(self):
        """
        Get the type of the input.

        Returns:
            String 'search'.
        """
        return "search"


class Url(Input):
    """
    URL input.

    See: <https://html.spec.whatwg.org/#url-state-(type=url)>

    Examples:
        >>> from web.form import Url
        >>> Url(name='url', value='url').render()
        u'<input id="url" name="url" type="url" value="url"/>'
    """

    def get_type(self):
        """
        Get the type of the input.

        Returns:
            String 'url'.
        """
        return "url"


class Number(Input):
    """
    Number input.

    See: <https://html.spec.whatwg.org/#number-state-(type=number)>

    Examples:
        >>> from web.form import Number
        >>> Number(name='num', min='0', max='10', step='2', value='5').render()
        u'<input id="num" max="10" min="0" name="num" step="2" type="number" value="5"/>'
    """

    def get_type(self):
        """
        Get the type of the input.

        Returns:
            String 'number'.
        """
        return "number"


class Range(Input):
    """
    Range input.

    See: <https://html.spec.whatwg.org/#range-state-(type=range)>

    Examples:
        >>> from web.form import Range
        >>> Range(name='range', min='0', max='10', step='2', value='5').render()
        u'<input id="range" max="10" min="0" name="range" step="2" type="range" value="5"/>'
    """

    def get_type(self):
        """
        Get the type of the input.

        Returns:
            String 'range'.
        """
        return "range"


class Color(Input):
    """
    Color input.

    Note: Not supported by Internet Explorer or Opera Mini

    See: <https://html.spec.whatwg.org/#color-state-(type=color)>

    Examples:
        >>> from web.form import Color
        >>> Color(name='color').render()
        u'<input id="color" name="color" type="color"/>'
    """

    def get_type(self):
        """
        Get the type of the input.

        Returns:
            String 'color'.
        """
        return "color"


class Datalist(Input):
    """
    Datalist input.

    This is currently supported by Chrome, Firefox, Edge, and Opera. It is not
    supported on Safari or Internet Explorer. Use it with caution.

    Datalist cannot be used separately. It must be bound to an input.

    <https://html.spec.whatwg.org/#the-datalist-element>

    Args:
        name: Name of the datalist.
        args: List of options for the datalist.
        *validators: Validators to apply to the input.
        **kwargs: Additional keyword arguments.

    Examples:
        >>> from web.form import Datalist
        >>> Datalist(name='list', args=[('a', 'b'), ('c', 'd')]).render()
        u'<datalist id="list" name="list"><option label="a" value="b"/><option label="c" value="d"/></datalist>'
        >>> Datalist(name='list', args=[['a', 'b'], ['c', 'd']]).render()
        u'<datalist id="list" name="list"><option label="a" value="b"/><option label="c" value="d"/></datalist>'
        >>> Datalist(name='list', args=['a', 'b', 'c', 'd']).render()
        u'<datalist id="list" name="list"><option value="a"/><option value="b"/><option value="c"/><option value="d"/></datalist>'
    """

    def __init__(self, name, args, *validators, **kwargs):
        """
        Initialize a Datalist instance.

        Args:
            name: Name of the datalist.
            args: List of options for the datalist.
            *validators: Validators to apply to the input.
            **kwargs: Additional keyword arguments.
        """
        self.args = args
        super().__init__(name, *validators, **kwargs)

    def render(self):
        """
        Render the HTML datalist element.

        Returns:
            String containing the rendered HTML datalist element.
        """
        attrs = self.attrs.copy()
        attrs["name"] = self.name
        label_p = ""
        x = "<datalist %s>" % attrs
        for arg in self.args:
            if isinstance(arg, (tuple, list)):
                label_p = ' label="%s"' % net.websafe(arg[0])
                label = net.websafe(arg[1])
            else:
                label = net.websafe(arg)
            x += f'<option{label_p} value="{label}"/>'
        x += "</datalist>"
        return x


class Validator:
    """
    Base validator class.

    Args:
        msg: Error message for validation failure.
        test: Function to test the value.
        jstest: JavaScript test function (optional).
    """

    def __deepcopy__(self, memo):
        """
        Create a deep copy of the validator.

        Args:
            memo: Memoization dictionary.

        Returns:
            A new Validator instance.
        """
        return copy.copy(self)

    def __init__(self, msg, test, jstest=None):
        """
        Initialize a Validator instance.

        Args:
            msg: Error message for validation failure.
            test: Function to test the value.
            jstest: JavaScript test function (optional).
        """
        utils.autoassign(self, locals())

    def valid(self, value):
        """
        Test if value is valid.

        Args:
            value: Value to test.

        Returns:
            Boolean indicating whether the value is valid.
        """
        try:
            return self.test(value)
        except:
            return False


notnull = Validator("Required", bool)


class regexp(Validator):
    """
    Regular expression validator.

    Args:
        rexp: Regular expression pattern.
        msg: Error message for validation failure.
    """

    def __init__(self, rexp, msg):
        """
        Initialize a regexp validator.

        Args:
            rexp: Regular expression pattern.
            msg: Error message for validation failure.
        """
        self.rexp = re.compile(rexp)
        self.msg = msg

    def valid(self, value):
        """
        Test if value matches the regular expression.

        Args:
            value: Value to test.

        Returns:
            Boolean indicating whether the value matches the pattern.
        """
        return bool(self.rexp.match(value))


if __name__ == "__main__":
    import doctest

    doctest.testmod()
