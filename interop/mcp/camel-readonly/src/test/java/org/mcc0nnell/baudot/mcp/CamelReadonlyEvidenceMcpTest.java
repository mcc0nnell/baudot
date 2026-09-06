package org.mcc0nnell.baudot.mcp;

import java.io.IOException;
import java.net.ServerSocket;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;

import io.modelcontextprotocol.client.McpClient;
import io.modelcontextprotocol.client.McpSyncClient;
import io.modelcontextprotocol.client.transport.HttpClientStreamableHttpTransport;
import io.modelcontextprotocol.spec.McpSchema;
import org.apache.camel.builder.RouteBuilder;
import org.apache.camel.main.Main;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

class CamelReadonlyEvidenceMcpTest {

    private static final Set<String> EXPECTED_TOOLS = Set.of(
            "inspect_dialog", "observe_sip_trace", "compare_sdp", "export_evidence");

    private static final Path FIXTURES = Path.of(System.getProperty("baudot.repo.root"))
            .resolve("testkit/mcp/fixtures/run-001").normalize();

    @Test
    void realCamelMcpMatchesDirectEvidenceFixtures() throws Exception {
        int port = freePort();
        Main main = new Main();
        main.configure().addRoutesBuilder(routes());
        main.addInitialProperty("camel.server.enabled", "true");
        main.addInitialProperty("camel.server.port", Integer.toString(port));
        main.addInitialProperty("camel.server.mcp-enabled", "true");
        main.addInitialProperty("camel.server.mcp-tags", "baudot-evidence-readonly");
        main.addInitialProperty("camel.server.mcp-server-name", "baudot-readonly-evidence");
        main.addInitialProperty("camel.server.mcp-tool-timeout", "5000");
        main.start();

        McpSyncClient client = null;
        try {
            client = McpClient.sync(HttpClientStreamableHttpTransport.builder("http://localhost:" + port).build())
                    .requestTimeout(Duration.ofSeconds(10))
                    .initializationTimeout(Duration.ofSeconds(10))
                    .build();

            McpSchema.InitializeResult init = client.initialize();
            assertEquals("baudot-readonly-evidence", init.serverInfo().name());

            var listed = client.listTools().tools();
            Map<String, McpSchema.Tool> byName = listed.stream()
                    .collect(Collectors.toMap(McpSchema.Tool::name, t -> t, (a, b) -> a, LinkedHashMap::new));
            assertEquals(EXPECTED_TOOLS, byName.keySet());

            for (McpSchema.Tool tool : byName.values()) {
                McpSchema.ToolAnnotations annotations = tool.annotations();
                assertNotNull(annotations, tool.name() + " annotations");
                assertEquals(Boolean.TRUE, annotations.readOnlyHint(), tool.name() + " readOnlyHint");
                assertEquals(Boolean.FALSE, annotations.destructiveHint(), tool.name() + " destructiveHint");
                assertEquals(Boolean.TRUE, annotations.idempotentHint(), tool.name() + " idempotentHint");
                assertEquals(Boolean.FALSE, annotations.openWorldHint(), tool.name() + " openWorldHint");
            }

            assertToolResult(client, "inspect_dialog", "inspect_dialog.json");
            assertToolResult(client, "observe_sip_trace", "observe_sip_trace.json");
            assertToolResult(client, "compare_sdp", "compare_sdp.json");
            assertToolResult(client, "export_evidence", "export_evidence.json");
        } finally {
            if (client != null) {
                client.closeGracefully();
            }
            main.stop();
        }
    }

    private static RouteBuilder routes() {
        return new RouteBuilder() {
            @Override
            public void configure() {
                readonlyTool("inspect_dialog", "Inspect preserved dialog evidence", "inspect_dialog.json");
                readonlyTool("observe_sip_trace", "Observe bounded preserved SIP trace", "observe_sip_trace.json");
                readonlyTool("compare_sdp", "Compare preserved SDP offer and answer evidence", "compare_sdp.json");
                readonlyTool("export_evidence", "Export preserved evidence references", "export_evidence.json");
            }

            private void readonlyTool(String name, String description, String fixture) {
                from("ai-tool:" + name
                     + "?tags=baudot-evidence-readonly"
                     + "&description=" + description.replace(" ", "%20")
                     + "&parameter.runId=string&parameter.runId.required=true"
                     + "&readOnlyHint=true&destructiveHint=false&idempotentHint=true&openWorldHint=false")
                        .process(exchange -> {
                            String runId = exchange.getMessage().getHeader("runId", String.class);
                            if (!"run-001".equals(runId)) {
                                throw new IllegalArgumentException("unknown synthetic runId");
                            }
                            exchange.getMessage().setBody(readFixture(fixture));
                        });
            }
        };
    }

    private static void assertToolResult(McpSyncClient client, String tool, String fixture) throws IOException {
        McpSchema.CallToolResult result = client.callTool(
                new McpSchema.CallToolRequest(tool, Map.of("runId", "run-001")));
        assertFalse(Boolean.TRUE.equals(result.isError()), tool + " returned MCP error");
        assertEquals(1, result.content().size(), tool + " content item count");
        assertTrue(result.content().get(0) instanceof McpSchema.TextContent, tool + " must return text content");
        String actual = ((McpSchema.TextContent) result.content().get(0)).text();
        assertEquals(readFixture(fixture), actual, tool + " must equal direct evidence fixture exactly");
    }

    private static String readFixture(String name) throws IOException {
        return Files.readString(FIXTURES.resolve(name));
    }

    private static int freePort() throws IOException {
        try (ServerSocket socket = new ServerSocket(0)) {
            return socket.getLocalPort();
        }
    }
}
