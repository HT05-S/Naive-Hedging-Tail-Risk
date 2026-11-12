"""Stage 1B data-construction package for the FRE 6123 tail-risk hedging project.

Modules
-------
config     market specifications, sample boundaries and fixed rules
io         read-only raw-data access and SHA-256 integrity guard
contracts  contract calendars, generic-to-contract mapping, held-contract rules
weekly     Wednesday observation selection and matched-contract weekly returns

Nothing in this package writes to data/raw/.
"""
