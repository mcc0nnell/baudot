package org.mcc0nnell.baudot.harness;

import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.InputStreamReader;
import java.io.OutputStreamWriter;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.KeyStore;
import java.security.MessageDigest;
import java.security.cert.X509Certificate;
import java.time.Duration;
import java.util.Collection;
import java.util.List;
import java.util.Map;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicReference;

import javax.net.ssl.KeyManagerFactory;
import javax.net.ssl.SSLContext;
import javax.net.ssl.SSLServerSocket;
import javax.net.ssl.SSLServerSocketFactory;
import javax.net.ssl.SSLSocket;
import javax.net.ssl.SSLSocketFactory;
import javax.net.ssl.TrustManagerFactory;

/**
 * Controlled RUE registration proof for the synthetic RFC 9248 registration lane.
 *
 * <p>The probe terminates an ephemeral self-signed TLS connection entirely on
 * loopback. It exercises a 401 Digest challenge followed by a verified REGISTER
 * and preserves only redacted signaling evidence. It is not production TLS,
 * PKI, SIP, RFC 5626, or RFC 9248 conformance evidence.</p>
 */
public final class RueRegistrationTlsProbe {
    private static final String SCENARIO = "RUE-REG-001";
    private static final String CORRELATION = "tls-register-v1";
    private static final Duration TIMEOUT = Duration.ofSeconds(8);

    private static final String DOMAIN = "provider-a.example";
    private static final String NUMBER = "+12025550101";
    private static final String USERNAME = "rue-001";
    private static final String PASSWORD = "baudot-secret";
    private static final String REALM = DOMAIN;
    private static final String NONCE = "baudot-nonce-001";
    private static final String CNONCE = "baudot-cnonce-001";
    private static final String NC = "00000001";
    private static final String QOP = "auth";
    private static final String REGISTER_URI = "sip:" + DOMAIN;

    private RueRegistrationTlsProbe() {
    }

    public static void main(String[] args) {
        int exit;
        try {
            exit = run();
        } catch (Throwable failure) {
            failure.printStackTrace(System.err);
            exit = 2;
        }
        System.exit(exit);
    }

    private static int run() throws Exception {
        Path evidenceRoot = Path.of(env("BAUDOT_EVIDENCE_DIR", "target/evidence"));
        Path keyStorePath = Path.of(requiredEnv("BAUDOT_RUE_REG_KEYSTORE"));
        char[] storePassword = requiredEnv("BAUDOT_RUE_REG_KEYSTORE_PASSWORD").toCharArray();
        String host = env("BAUDOT_RUE_REG_HOST", "127.0.0.1");
        int port = Integer.parseInt(env("BAUDOT_RUE_REG_PORT", "5161"));
        String selectedTransport = env("BAUDOT_RUE_REG_TRANSPORT", "tls");
        if (!"tls".equals(selectedTransport)) {
            throw new IllegalStateException("RUE-REG-001 requires the selected discovery transport to be tls");
        }

        SSLContext context = sslContext(keyStorePath, storePassword);
        AtomicReference<Throwable> serverFailure = new AtomicReference<>();
        AtomicBoolean initialRegisterObserved = new AtomicBoolean();
        AtomicBoolean outboundHeaderObserved = new AtomicBoolean();
        AtomicBoolean contactObObserved = new AtomicBoolean();
        AtomicBoolean digestResponseVerified = new AtomicBoolean();
        AtomicBoolean authenticatedRegisterObserved = new AtomicBoolean();
        AtomicBoolean registrationAccepted = new AtomicBoolean();
        CountDownLatch listening = new CountDownLatch(1);

        try (EvidenceRecorder evidence = new EvidenceRecorder(
                evidenceRoot, SCENARIO, CORRELATION, "registration-proof")) {

            Thread server = new Thread(() -> {
                try {
                    runServer(
                            context,
                            host,
                            port,
                            evidence,
                            listening,
                            initialRegisterObserved,
                            outboundHeaderObserved,
                            contactObObserved,
                            digestResponseVerified,
                            authenticatedRegisterObserved);
                } catch (Throwable failure) {
                    serverFailure.set(failure);
                    listening.countDown();
                }
            }, "baudot-rue-registration-provider");
            server.setDaemon(true);
            server.start();

            if (!listening.await(TIMEOUT.toMillis(), TimeUnit.MILLISECONDS)) {
                throw new IllegalStateException("synthetic provider TLS listener did not start");
            }
            if (serverFailure.get() != null) {
                throw new IllegalStateException("synthetic provider failed before registration", serverFailure.get());
            }

            SSLSocketFactory clientFactory = context.getSocketFactory();
            try (SSLSocket client = (SSLSocket) clientFactory.createSocket(host, port)) {
                client.setSoTimeout((int) TIMEOUT.toMillis());
                client.startHandshake();

                X509Certificate peer = (X509Certificate) client.getSession().getPeerCertificates()[0];
                boolean domainInCertificate = certificateContainsDnsName(peer, DOMAIN);
                evidence.event("registration.tls.handshake", Map.of(
                        "protocol", client.getSession().getProtocol(),
                        "cipherSuite", client.getSession().getCipherSuite(),
                        "providerDomainInCertificate", Boolean.toString(domainInCertificate),
                        "trustBoundary", "ephemeral-self-signed-loopback-only"));
                require(domainInCertificate, "synthetic TLS certificate is not bound to provider domain");

                BufferedReader in = new BufferedReader(new InputStreamReader(client.getInputStream(), StandardCharsets.UTF_8));
                BufferedWriter out = new BufferedWriter(new OutputStreamWriter(client.getOutputStream(), StandardCharsets.UTF_8));

                String first = register(false, null);
                writeMessage(out, first);
                evidence.writeBytes("register-initial.request.sip", first.getBytes(StandardCharsets.UTF_8));

                String challenge = readMessage(in);
                evidence.writeBytes("register-401.response.sip", challenge.getBytes(StandardCharsets.UTF_8));
                require(challenge.startsWith("SIP/2.0 401"), "synthetic provider did not challenge initial REGISTER");
                require(challenge.contains("WWW-Authenticate: Digest"), "Digest challenge missing");
                require(challenge.contains("nonce=\"" + NONCE + "\""), "Digest nonce drift");

                String authorization = digestAuthorization();
                String second = register(true, authorization);
                writeMessage(out, second);
                evidence.writeBytes(
                        "register-authenticated.request.redacted.sip",
                        redactAuthorization(second).getBytes(StandardCharsets.UTF_8));

                String ok = readMessage(in);
                evidence.writeBytes("register-200.response.sip", ok.getBytes(StandardCharsets.UTF_8));
                registrationAccepted.set(ok.startsWith("SIP/2.0 200"));
                require(registrationAccepted.get(), "synthetic provider did not accept challenged REGISTER");

                evidence.event("registration.client.result", Map.of(
                        "challengeObserved", "true",
                        "authenticatedRegisterSent", "true",
                        "registrationAccepted", Boolean.toString(registrationAccepted.get()),
                        "authorizationEvidenceRedacted", "true"));
            }

            server.join(TIMEOUT.toMillis());
            if (serverFailure.get() != null) {
                throw new IllegalStateException("synthetic provider registration server failed", serverFailure.get());
            }

            boolean pass = initialRegisterObserved.get()
                    && outboundHeaderObserved.get()
                    && contactObObserved.get()
                    && digestResponseVerified.get()
                    && authenticatedRegisterObserved.get()
                    && registrationAccepted.get();

            evidence.result(Map.ofEntries(
                    Map.entry("scenario.id", SCENARIO),
                    Map.entry("correlation.id", CORRELATION),
                    Map.entry("provider.domain", DOMAIN),
                    Map.entry("registered.number", NUMBER),
                    Map.entry("discovery.transport", selectedTransport),
                    Map.entry("tls.handshake.observed", "true"),
                    Map.entry("tls.provider.domain.certificate.bound", "true"),
                    Map.entry("register.initial.observed", Boolean.toString(initialRegisterObserved.get())),
                    Map.entry("register.digest.challenge.observed", "true"),
                    Map.entry("register.digest.response.verified", Boolean.toString(digestResponseVerified.get())),
                    Map.entry("register.authenticated.observed", Boolean.toString(authenticatedRegisterObserved.get())),
                    Map.entry("register.accepted", Boolean.toString(registrationAccepted.get())),
                    Map.entry("sip.supported.outbound.observed", Boolean.toString(outboundHeaderObserved.get())),
                    Map.entry("contact.ob.parameter.observed", Boolean.toString(contactObObserved.get())),
                    Map.entry("rfc5626.outbound.flow.proven", "false"),
                    Map.entry("authorization.evidence.redacted", "true"),
                    Map.entry("live.tnd.queried", "false"),
                    Map.entry("live.dns.queried", "false"),
                    Map.entry("transport.claim", "ephemeral-self-signed-loopback-tls-only"),
                    Map.entry("claim", "challenged-rue-registration-observation-only"),
                    Map.entry("scenario.result", pass ? "PASS" : "FAIL")));

            return pass ? 0 : 3;
        }
    }

    private static void runServer(
            SSLContext context,
            String host,
            int port,
            EvidenceRecorder evidence,
            CountDownLatch listening,
            AtomicBoolean initialRegisterObserved,
            AtomicBoolean outboundHeaderObserved,
            AtomicBoolean contactObObserved,
            AtomicBoolean digestResponseVerified,
            AtomicBoolean authenticatedRegisterObserved) throws Exception {
        SSLServerSocketFactory factory = context.getServerSocketFactory();
        try (SSLServerSocket server = (SSLServerSocket) factory.createServerSocket(port, 1, java.net.InetAddress.getByName(host))) {
            server.setSoTimeout((int) TIMEOUT.toMillis());
            listening.countDown();
            try (SSLSocket socket = (SSLSocket) server.accept()) {
                socket.setSoTimeout((int) TIMEOUT.toMillis());
                socket.startHandshake();
                BufferedReader in = new BufferedReader(new InputStreamReader(socket.getInputStream(), StandardCharsets.UTF_8));
                BufferedWriter out = new BufferedWriter(new OutputStreamWriter(socket.getOutputStream(), StandardCharsets.UTF_8));

                String first = readMessage(in);
                initialRegisterObserved.set(first.startsWith("REGISTER " + REGISTER_URI + " SIP/2.0"));
                outboundHeaderObserved.set(headerContains(first, "Supported", "outbound"));
                contactObObserved.set(headerContains(first, "Contact", ";ob"));
                require(initialRegisterObserved.get(), "initial REGISTER target drift");
                require(outboundHeaderObserved.get(), "Supported: outbound missing");
                require(contactObObserved.get(), "Contact ;ob parameter missing");

                writeMessage(out, response401(first));

                String second = readMessage(in);
                authenticatedRegisterObserved.set(second.startsWith("REGISTER " + REGISTER_URI + " SIP/2.0"));
                String authorization = headerValue(second, "Authorization");
                digestResponseVerified.set(authorization != null && authorization.equals(digestAuthorization()));
                require(authenticatedRegisterObserved.get(), "authenticated REGISTER target drift");
                require(digestResponseVerified.get(), "Digest response did not verify") ;

                evidence.event("registration.provider.verify", Map.of(
                        "initialRegisterObserved", Boolean.toString(initialRegisterObserved.get()),
                        "outboundHeaderObserved", Boolean.toString(outboundHeaderObserved.get()),
                        "contactObObserved", Boolean.toString(contactObObserved.get()),
                        "authenticatedRegisterObserved", Boolean.toString(authenticatedRegisterObserved.get()),
                        "digestResponseVerified", Boolean.toString(digestResponseVerified.get()),
                        "authorizationValuePreserved", "false"));

                writeMessage(out, response200(second));
            }
        }
    }

    private static SSLContext sslContext(Path keyStorePath, char[] password) throws Exception {
        KeyStore store = KeyStore.getInstance("PKCS12");
        try (var in = Files.newInputStream(keyStorePath)) {
            store.load(in, password);
        }
        KeyManagerFactory kmf = KeyManagerFactory.getInstance(KeyManagerFactory.getDefaultAlgorithm());
        kmf.init(store, password);
        TrustManagerFactory tmf = TrustManagerFactory.getInstance(TrustManagerFactory.getDefaultAlgorithm());
        tmf.init(store);
        SSLContext context = SSLContext.getInstance("TLS");
        context.init(kmf.getKeyManagers(), tmf.getTrustManagers(), null);
        return context;
    }

    private static boolean certificateContainsDnsName(X509Certificate certificate, String expected) throws Exception {
        Collection<List<?>> names = certificate.getSubjectAlternativeNames();
        if (names == null) {
            return false;
        }
        for (List<?> entry : names) {
            if (entry.size() >= 2 && Integer.valueOf(2).equals(entry.get(0)) && expected.equalsIgnoreCase(String.valueOf(entry.get(1)))) {
                return true;
            }
        }
        return false;
    }

    private static String register(boolean authenticated, String authorization) {
        String branch = authenticated ? "z9hG4bK-baudot-reg-auth" : "z9hG4bK-baudot-reg-initial";
        int cseq = authenticated ? 2 : 1;
        StringBuilder message = new StringBuilder();
        message.append("REGISTER ").append(REGISTER_URI).append(" SIP/2.0\r\n");
        message.append("Via: SIP/2.0/TLS 127.0.0.1:5171;branch=").append(branch).append(";rport\r\n");
        message.append("Max-Forwards: 70\r\n");
        message.append("From: <sip:").append(NUMBER).append('@').append(DOMAIN).append(">;tag=baudot-rue-reg\r\n");
        message.append("To: <sip:").append(NUMBER).append('@').append(DOMAIN).append(">\r\n");
        message.append("Call-ID: baudot-rue-reg-001@127.0.0.1\r\n");
        message.append("CSeq: ").append(cseq).append(" REGISTER\r\n");
        message.append("Contact: <sip:").append(NUMBER)
                .append("@127.0.0.1:5171;transport=tls>;reg-id=1;+sip.instance=\"<urn:uuid:00000000-0000-4000-8000-000000000001>\";ob\r\n");
        message.append("Supported: outbound\r\n");
        message.append("Expires: 300\r\n");
        if (authenticated && authorization != null) {
            message.append("Authorization: ").append(authorization).append("\r\n");
        }
        message.append("Content-Length: 0\r\n\r\n");
        return message.toString();
    }

    private static String response401(String request) {
        return responseBase(request, 401, "Unauthorized")
                + "WWW-Authenticate: Digest realm=\"" + REALM + "\", nonce=\"" + NONCE
                + "\", algorithm=MD5, qop=\"auth\"\r\nContent-Length: 0\r\n\r\n";
    }

    private static String response200(String request) {
        return responseBase(request, 200, "OK")
                + "Supported: outbound\r\nExpires: 300\r\nContent-Length: 0\r\n\r\n";
    }

    private static String responseBase(String request, int status, String reason) {
        StringBuilder response = new StringBuilder("SIP/2.0 ").append(status).append(' ').append(reason).append("\r\n");
        appendResponseHeader(response, request, "Via");
        appendResponseHeader(response, request, "From");
        appendResponseHeader(response, request, "To");
        appendResponseHeader(response, request, "Call-ID");
        appendResponseHeader(response, request, "CSeq");
        return response.toString();
    }

    private static void appendResponseHeader(StringBuilder response, String request, String name) {
        String value = headerValue(request, name);
        if (value != null) {
            response.append(name).append(": ").append(value).append("\r\n");
        }
    }

    private static String digestAuthorization() throws Exception {
        String ha1 = md5(USERNAME + ":" + REALM + ":" + PASSWORD);
        String ha2 = md5("REGISTER:" + REGISTER_URI);
        String response = md5(ha1 + ":" + NONCE + ":" + NC + ":" + CNONCE + ":" + QOP + ":" + ha2);
        return "Digest username=\"" + USERNAME + "\", realm=\"" + REALM + "\", nonce=\"" + NONCE
                + "\", uri=\"" + REGISTER_URI + "\", response=\"" + response + "\", algorithm=MD5, qop="
                + QOP + ", nc=" + NC + ", cnonce=\"" + CNONCE + "\"";
    }

    private static String md5(String value) throws Exception {
        MessageDigest digest = MessageDigest.getInstance("MD5");
        byte[] bytes = digest.digest(value.getBytes(StandardCharsets.UTF_8));
        StringBuilder result = new StringBuilder();
        for (byte b : bytes) {
            result.append(String.format("%02x", b));
        }
        return result.toString();
    }

    private static void writeMessage(BufferedWriter out, String message) throws Exception {
        out.write(message);
        out.flush();
    }

    private static String readMessage(BufferedReader in) throws Exception {
        StringBuilder message = new StringBuilder();
        int contentLength = 0;
        while (true) {
            String line = in.readLine();
            if (line == null) {
                throw new IllegalStateException("unexpected EOF while reading SIP message");
            }
            message.append(line).append("\r\n");
            if (line.regionMatches(true, 0, "Content-Length:", 0, "Content-Length:".length())) {
                contentLength = Integer.parseInt(line.substring(line.indexOf(':') + 1).trim());
            }
            if (line.isEmpty()) {
                break;
            }
        }
        if (contentLength > 0) {
            char[] body = new char[contentLength];
            int offset = 0;
            while (offset < contentLength) {
                int count = in.read(body, offset, contentLength - offset);
                if (count < 0) {
                    throw new IllegalStateException("unexpected EOF while reading SIP body");
                }
                offset += count;
            }
            message.append(body);
        }
        return message.toString();
    }

    private static String headerValue(String message, String name) {
        String prefix = name.toLowerCase() + ":";
        for (String line : message.split("\\r?\\n")) {
            if (line.toLowerCase().startsWith(prefix)) {
                return line.substring(line.indexOf(':') + 1).trim();
            }
        }
        return null;
    }

    private static boolean headerContains(String message, String name, String token) {
        String value = headerValue(message, name);
        return value != null && value.contains(token);
    }

    private static String redactAuthorization(String message) {
        return message.replaceAll("(?im)^Authorization:.*$", "Authorization: Digest [redacted]");
    }

    private static String env(String name, String fallback) {
        String value = System.getenv(name);
        return value == null || value.isBlank() ? fallback : value;
    }

    private static String requiredEnv(String name) {
        String value = System.getenv(name);
        if (value == null || value.isBlank()) {
            throw new IllegalStateException("missing required environment variable: " + name);
        }
        return value;
    }

    private static void require(boolean condition, String message) {
        if (!condition) {
            throw new IllegalStateException(message);
        }
    }
}
