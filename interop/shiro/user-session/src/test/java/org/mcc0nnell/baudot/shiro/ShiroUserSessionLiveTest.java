package org.mcc0nnell.baudot.shiro;

import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Set;

import org.apache.shiro.authc.IncorrectCredentialsException;
import org.apache.shiro.authc.UnknownAccountException;
import org.apache.shiro.authc.UsernamePasswordToken;
import org.apache.shiro.mgt.DefaultSecurityManager;
import org.apache.shiro.realm.SimpleAccountRealm;
import org.apache.shiro.subject.Subject;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ShiroUserSessionLiveTest {

    private static final String USER = "provider-a-operator";
    private static final String PASSWORD = "synthetic-password-only";

    @Test
    void authenticatedSubjectProjectsMinimalActorContextAndLogoutInvalidatesSession() {
        DefaultSecurityManager securityManager = securityManager();
        Subject subject = new Subject.Builder(securityManager).buildSubject();

        assertFalse(subject.isAuthenticated());
        assertFalse(subject.isRemembered());
        assertNull(subject.getSession(false));

        subject.login(new UsernamePasswordToken(USER, PASSWORD));

        assertTrue(subject.isAuthenticated());
        assertFalse(subject.isRemembered(), "current login is authenticated, not remembered-only");
        assertEquals(USER, subject.getPrincipal());
        assertTrue(subject.hasRole("provider-operator"));
        assertTrue(subject.hasRole("itrs-reader"));

        var session = subject.getSession();
        assertNotNull(session.getId());

        Map<String, Object> actor = projectActorContext(subject);
        assertEquals(
                Set.of("actorId", "actorType", "tenantId", "providerId", "roles", "sessionId", "authenticatedAt", "authenticationStrength"),
                actor.keySet());
        assertEquals(USER, actor.get("actorId"));
        assertEquals("provider-user", actor.get("actorType"));
        assertEquals("tenant-provider-a", actor.get("tenantId"));
        assertEquals("provider-a", actor.get("providerId"));
        assertEquals("authenticated", actor.get("authenticationStrength"));
        assertFalse(actor.containsKey("password"));
        assertFalse(actor.containsKey("telephoneNumber"));
        assertFalse(actor.containsKey("subscriberId"));
        assertFalse(actor.containsKey("eligibilityApproved"));

        subject.logout();

        assertFalse(subject.isAuthenticated());
        assertFalse(subject.isRemembered());
        assertNull(subject.getSession(false), "logout must not leave an active subject session");
    }

    @Test
    void invalidCredentialsNeverCreateAuthenticatedActorContext() {
        DefaultSecurityManager securityManager = securityManager();
        Subject subject = new Subject.Builder(securityManager).buildSubject();

        assertThrows(
                IncorrectCredentialsException.class,
                () -> subject.login(new UsernamePasswordToken(USER, "wrong-password")));

        assertFalse(subject.isAuthenticated());
        assertFalse(subject.isRemembered());
        assertNull(subject.getSession(false));
    }

    @Test
    void unknownAccountNeverCreatesAuthenticatedActorContext() {
        DefaultSecurityManager securityManager = securityManager();
        Subject subject = new Subject.Builder(securityManager).buildSubject();

        assertThrows(
                UnknownAccountException.class,
                () -> subject.login(new UsernamePasswordToken("unknown-actor", PASSWORD)));

        assertFalse(subject.isAuthenticated());
        assertNull(subject.getSession(false));
    }

    private static DefaultSecurityManager securityManager() {
        SimpleAccountRealm realm = new SimpleAccountRealm("baudot-synthetic-realm");
        realm.addAccount(USER, PASSWORD, "provider-operator", "itrs-reader");
        return new DefaultSecurityManager(realm);
    }

    private static Map<String, Object> projectActorContext(Subject subject) {
        if (!subject.isAuthenticated()) {
            throw new IllegalStateException("protected actor context requires authenticated Shiro subject");
        }
        Map<String, Object> actor = new LinkedHashMap<>();
        actor.put("actorId", subject.getPrincipal().toString());
        actor.put("actorType", "provider-user");
        actor.put("tenantId", "tenant-provider-a");
        actor.put("providerId", "provider-a");
        actor.put("roles", Set.of("provider-operator", "itrs-reader"));
        actor.put("sessionId", subject.getSession().getId().toString());
        actor.put("authenticatedAt", Instant.now().toString());
        actor.put("authenticationStrength", "authenticated");
        return actor;
    }
}
