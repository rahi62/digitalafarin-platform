import { afterEach, describe, expect, it } from "vitest";
import { config } from "../config.js";
import { createCsrfToken, verifyCsrfToken } from "./csrf.js";
import { hashPassword, verifyPassword } from "./password.js";
import { hashOpaqueToken } from "./session.js";

const originalCsrfSecret = config.csrfSecret;

afterEach(() => {
  config.csrfSecret = originalCsrfSecret;
});

describe("Agency authentication primitives", () => {
  it("hashes passwords with a verifiable one-way hash", async () => {
    const password = "correct-horse-battery-staple";
    const hash = await hashPassword(password);
    expect(hash).not.toContain(password);
    await expect(verifyPassword(hash, password)).resolves.toBe(true);
    await expect(verifyPassword(hash, "incorrect-password-value")).resolves.toBe(false);
  });

  it("never uses the raw opaque session token as the database lookup value", () => {
    const token = "opaque-session-token";
    const hashed = hashOpaqueToken(token);
    expect(hashed).not.toBe(token);
    expect(hashed).toMatch(/^[a-f0-9]{64}$/);
    expect(hashOpaqueToken(token)).toBe(hashed);
  });

  it("binds CSRF tokens to the current session token", () => {
    config.csrfSecret = "a-production-like-secret-that-is-longer-than-32-characters";
    const tokenA = createCsrfToken("session-a");
    const tokenB = createCsrfToken("session-b");
    expect(tokenA).not.toBe(tokenB);
    expect(verifyCsrfToken("session-a", tokenA)).toBe(true);
    expect(verifyCsrfToken("session-b", tokenA)).toBe(false);
  });
});
