import path from "node:path";
import { migrate } from "drizzle-orm/postgres-js/migrator";
import { closeDb, getDb } from "./client.js";

async function main() {
  const db = getDb();
  await migrate(db, { migrationsFolder: path.resolve("drizzle") });
  console.log("Agency database migrations applied successfully.");
}

main()
  .catch((error) => {
    console.error("Agency database migration failed:", error instanceof Error ? error.message : error);
    process.exitCode = 1;
  })
  .finally(async () => {
    await closeDb();
  });
