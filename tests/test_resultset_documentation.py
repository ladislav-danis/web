"""Execute the result-set Markdown example unchanged, offline and bounded."""
from .test_readme_contract import probe


def test_resultset_markdown_example_bytes(tmp_path, record_property):
    probe(r'''
        import hashlib
        import re
        path = Path(web.__file__).with_name('docs') / 'db.md'
        markdown = path.read_bytes()
        section = markdown.split(b'#### Executable SQLite example\n', 1)[1].split(b'### `Transaction`', 1)[0]
        fences = re.findall(rb'^```python\n(.*?)^```', section, re.M | re.S)
        assert len(fences) == 1
        source = fences[0]
        # This example must never connect to a real application database,
        # even if a future documentation edit accidentally adds a path.
        opened = []
        def memory_only(event, args):
            if event == 'sqlite3.connect':
                assert args[0] == ':memory:', 'Only owned in-memory SQLite allowed'
                opened.append(args[0])
        sys.addaudithook(memory_only)
        namespace = {'__name__': '__main__'}
        exec(compile(source, str(path) + ':Executable SQLite example', 'exec'), namespace)
        assert opened == [':memory:']
        assert [row.n for row in namespace['rows']] == [1, 2, 3, 4]
        assert namespace['result']._index == namespace['remaining']._index == 4
        print(json.dumps({'fence_sha256': hashlib.sha256(source).hexdigest(),
                          'rows': [row.n for row in namespace['rows']],
                          'databases': opened}))
    ''', tmp_path, record_property)
