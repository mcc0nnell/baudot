package org.mcc0nnell.baudot.tilden;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.SerializationFeature;

import java.nio.file.Files;
import java.nio.file.Path;

/** Small process boundary for converting TildenSelection evidence into BaudotRoute JSON. */
public final class TildenSelectionMain {
    private TildenSelectionMain() {
    }

    public static void main(String[] args) throws Exception {
        if (args.length < 1 || args.length > 2) {
            System.err.println("usage: TildenSelectionMain <selection.json> [route.json]");
            System.exit(2);
        }

        BaudotRoute route = new TildenSelectionAdapter().read(Path.of(args[0]));
        ObjectMapper mapper = new ObjectMapper().enable(SerializationFeature.INDENT_OUTPUT);
        byte[] encoded = mapper.writeValueAsBytes(route);

        if (args.length == 2) {
            Path output = Path.of(args[1]);
            Path parent = output.getParent();
            if (parent != null) {
                Files.createDirectories(parent);
            }
            Files.write(output, encoded);
        } else {
            System.out.write(encoded);
            System.out.write('\n');
        }
    }
}
