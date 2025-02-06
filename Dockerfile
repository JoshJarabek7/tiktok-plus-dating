# Add to Dockerfile for Neo4j
ENV NEO4J_apoc_export_file_enabled=true
ENV NEO4J_apoc_import_file_enabled=true
ENV NEO4JLABS_PLUGINS='["apoc", "graph-data-science"]'