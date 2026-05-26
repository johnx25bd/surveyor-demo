"""Analysis operations — typed dataset→dataset transforms the agent composes (architecture §7).

Each op reads inputs from the store by handle, writes a new dataset, and returns a descriptor.
A new analytical capability is a new op implementing the Tool contract — no existing code changes.
"""
