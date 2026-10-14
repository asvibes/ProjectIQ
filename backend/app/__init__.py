"""ProjectIQ backend package.

Intentionally free of imports: ``app.database`` builds a database engine at import time,
so importing it (or ``app.main``) from here would create side effects and import cycles
for every submodule. Import what you need from the submodule directly.
"""

__version__ = "0.1.0"