# Xian Contracting Linter

A linting tool for Xian smart contracts, compatible with both standard Python environments and Pyodide.

### Requirement
python>=3.11
pyflakes==3.2.0


### Build
pip install and use python-build
```
python -m build -n
```
built files will be found in `dist` folder


### Pyodide Usage
```python
import micropip
await micropip.install('xian_contracting_linter')
from xian_contracting_linter import lint_code

# Example usage
code = '''
@export
def my_function():
	pass
'''
result = lint_code(code)
```

## Features

- Smart contract syntax validation
- Export decorator checking
- ORM usage validation
- Built-in security checks
- Pyodide compatibility for browser-based usage