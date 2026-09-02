# Command-route compatibility

A compatibility alias is an installed legacy route with a preferred canonical form. The legacy
route keeps its argument grammar, confirmation gates, side effects, durable outputs, and host
availability; its migration notice does not invoke or forward to another host command.

The deprecation clock starts independently for each payload only when its first containing release
is published. Published releases ca 2.16.0, ca-codex 0.8.0, and ca-pi 0.9.0 predate this registry and
do not contain the compatibility metadata, so no clock has started. The first later published release
that contains it starts that payload's clock. ca retains these routes through every 2.x release, with
no removal before a separately approved 3.0.0. ca-codex and ca-pi retain them through every later
0.x release, with no removal before a separately approved 1.0.0. Passing a version floor never
authorizes removal: removal needs a new governed decision and frozen-route compatibility evidence.
