package org.mcc0nnell.baudot.itrs;

import java.util.Map;

public final class ItrsCteSessions {
    public static final String PROVIDER_A_TOKEN = "baudot-cte-provider-a";
    public static final String PROVIDER_B_TOKEN = "baudot-cte-provider-b";
    public static final String URD_AUTHORITY_TOKEN = "baudot-cte-urd-authority";

    private static final Map<String, Session> SESSIONS = Map.of(
            PROVIDER_A_TOKEN, new Session("provider-a-session", Role.PROVIDER, "XSPID-A"),
            PROVIDER_B_TOKEN, new Session("provider-b-session", Role.PROVIDER, "XSPID-B"),
            URD_AUTHORITY_TOKEN, new Session("urd-authority-session", Role.URD_AUTHORITY, null));

    private ItrsCteSessions() { }

    public static Session authenticate(String authorization) {
        if (authorization == null || !authorization.startsWith("Bearer ")) return null;
        return SESSIONS.get(authorization.substring("Bearer ".length()).trim());
    }

    public enum Role { PROVIDER, URD_AUTHORITY }
    public record Session(String id, Role role, String xspid) { }
}
