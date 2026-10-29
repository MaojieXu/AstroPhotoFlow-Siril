# Agent usage

1. Call list_nodes(query="stretch"), then get_node with its definition_id.
2. Read list_canvas_pages and get_canvas for the intended page. Reading never grants control; the user must explicitly hand over the active canvas.
3. Submit edit_canvas with a new operation_id, the exact page/workflow/graph IDs and current content/control tokens, and edit={"action":"add_node","definition_id":"169de083-7f81-4cde-a329-5541ecacf463","parameters":{"linked":false,"shadowsclip":-2.8,"targetbg":0.25}}.
4. Use the actual returned node_id and new content_token. Connect the source APF_SCIENCE science port to the new node image port with a separate connect operation.
5. Use set_parameter with the actual node_id to adjust parameters. Preserve zero; shadowsclip supports finite negative values, targetbg is 0..1.
6. Unknown results must be queried with the same operation_id, not replayed. A manual edit or reconnect revokes control. Canvas editing does not submit execution.

Quick preview uses a 1024px linear sample. Formal execution reads original scientific files, creates new FITS, and displays results without a second automatic stretch. Ordered groups retain their fixed member order. The 199 reference commands are not executable nodes.
