# Intentional break for recovery testing: raise an error when the mappers package is imported.
# This simulates a faulty deployment where mapper initialization fails.
raise RuntimeError("Simulated mappers package import failure for recovery testing")
