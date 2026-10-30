# Agent usage

The candidate requires platform SDK v2. Discover the installed fixed definition with `list_nodes` / `get_node`; do not assume the default catalog already contains this unpublished Bundle. Read each operation's typed ports, parameter contract, dependencies, examples and `reference/coverage.json`. `APF_SCIENCE` carries fixed image/sequence references; `APF_FILE` carries fixed library files or checked artifacts. Native growing inputs are used for Merge / Stack All. An optional input is disconnected when omitted; numeric zero is not omission.

1. Call list_nodes(query="stretch"), then get_node with its definition_id.
2. Read list_canvas_pages and get_canvas for the intended page. Reading never grants control; the user must explicitly hand over the active canvas.
3. Submit edit_canvas with a new operation_id, the exact page/workflow/graph IDs and current content/control tokens, and edit={"action":"add_node","definition_id":"169de083-7f81-4cde-a329-5541ecacf463","parameters":{"linked":false,"shadowsclip":-2.8,"targetbg":0.25}}.
4. Use the actual returned node_id and new content_token. Connect the source APF_SCIENCE science port to the new node image port with a separate connect operation.
5. Use set_parameter with the actual node_id to adjust parameters. Preserve zero; shadowsclip supports finite negative values, targetbg is 0..1.
6. Query an uncertain canvas edit with `get_canvas_request` and the same operation_id; do not replay it. A manual edit or reconnect revokes control. Canvas editing does not submit execution. Choose an explicit export, analysis or stacking endpoint for transforms; only declared endpoint dependencies execute.

Quick preview is available only where the operation declares it and uses a 1024px linear sample. Formal execution reads originals and creates checked full scientific files. Ordered groups retain fixed membership and order; preview pixels never become science inputs. The shared result viewer handles selected outputs, members, HDUs, pan/zoom, display thresholds, tables and plots without registering new materials or changing graph control.

For an actual native prompt, use `list_run_calls(prompt_id, node_id=...)`, `get_run_call(prompt_id, call_id)` and `get_run_analysis(prompt_id, call_id, output_index, member_index)` to read the recorded version/commit, observation, checked ports and normalized analysis. The Python client, CLI `run-calls` and MCP share those read capabilities. They do not add an Agent queue/execution authority. Unknown process state must be queried before any decision to run again; missing results are not zero measurements. Full report/log artifacts remain available alongside bounded display tables.

All 199 reference entries retain coverage. 181 scriptable commands are implemented through 160 real operations plus explicit session/IO/runtime mappings; non-scriptable commands remain non-executable with documented viewing alternatives or deferred GUI behavior.
