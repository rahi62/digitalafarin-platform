import { drizzle, type PostgresJsDatabase } from "drizzle-orm/postgres-js";
import postgres, { type Sql } from "postgres";
import { config } from "../config.js";
import * as schema from "./schema.js";

let sqlClient: Sql | null = null;
let database: PostgresJsDatabase<typeof schema> | null = null;

export function getDb(): PostgresJsDatabase<typeof schema> {
  if (database) return database;
  if (!config.databaseUrl) {
    throw new Error("DATABASE_URL is required for PostgreSQL operations");
  }

  sqlClient = postgres(config.databaseUrl, {
    max: 10,
    idle_timeout: 20,
    connect_timeout: 10,
    prepare: false,
  });
  database = drizzle(sqlClient, { schema });
  return database;
}

export async function closeDb(): Promise<void> {
  if (sqlClient) {
    await sqlClient.end({ timeout: 5 });
  }
  sqlClient = null;
  database = null;
}
