import { defineConfig } from "@prisma/config";

export default defineConfig({
  schema: "./prisma/schema.prisma",
  datasource: {
    url: process.env.POSTGRES_PRISMA_URL || process.env.DATABASE_URL || "",
  },
  migrate: {
    url: process.env.POSTGRES_PRISMA_URL || process.env.DATABASE_URL || "",
  },
});
