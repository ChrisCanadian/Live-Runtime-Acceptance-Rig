"""Full-runtime Nexus Synapse flight-control acceptance target.

This package is deliberately separate from the Discord surface acceptance lane.
It enters the kernelized host through the canonical /v1/chat/completions runtime
boundary and treats all 17 declared kernel responsibilities as required flight
controls for a full GREEN result.
"""
