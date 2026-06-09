"""agents/capabilities/post_steps — declared after-step capabilities (§9 / CR-06).

A ``post_step`` capability runs once a step's execution strategy has finished. The
kernel resolves it by name from ``Step.post_step`` and invokes ``run(step, ctx)``
— replacing the kernel-resident prototype-revision validation block (07-10).
"""
