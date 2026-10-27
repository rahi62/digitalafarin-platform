import express from "express";
import { afterEach, describe, expect, it } from "vitest";
import type { Server } from "node:http";
import { createAdminApiRouter } from "./http.js";

let server: Server | undefined;

afterEach(async () => {
  if (!server) return;
  await new Promise<void>((resolve, reject) => server?.close((error) => (error ? reject(error) : resolve())));
  server = undefined;
});

async function startApi() {
  const app = express();
  app.use(express.json());
  app.use("/api/v1", createAdminApiRouter());
  server = app.listen(0, "127.0.0.1");
  await new Promise<void>((resolve) => server?.once("listening", () => resolve()));
  const address = server.address();
  if (!address || typeof address === "string") throw new Error("Unable to resolve test server address");
  return `http://127.0.0.1:${address.port}`;
}

describe("Agency REST API composition", () => {
  it("mounts the auth API and protects /auth/me", async () => {
    const origin = await startApi();
    const response = await fetch(`${origin}/api/v1/auth/me`);
    expect(response.status).toBe(401);
    expect(await response.json()).toEqual({
      data: null,
      error: { code: "AUTH_REQUIRED", message: "Authentication required" },
    });
  });
});
