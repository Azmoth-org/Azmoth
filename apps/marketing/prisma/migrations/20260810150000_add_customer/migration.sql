-- Billable client profiles (LucaP-flavored: company, contacts, billing
-- addresses, tax identifier) — the agency's invoicing data.
CREATE TABLE "customer" (
    "id" TEXT NOT NULL,
    "userId" TEXT,
    "displayName" TEXT NOT NULL,
    "title" TEXT,
    "givenName" TEXT,
    "familyName" TEXT,
    "companyName" TEXT,
    "primaryEmail" TEXT,
    "alternateEmail" TEXT,
    "primaryPhone" TEXT,
    "mobile" TEXT,
    "webAddress" TEXT,
    "taxIdentifier" TEXT,
    "billingAddress" JSONB,
    "shippingAddress" JSONB,
    "notes" TEXT,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "customer_pkey" PRIMARY KEY ("id")
);

CREATE UNIQUE INDEX "customer_userId_key" ON "customer"("userId");
CREATE INDEX "customer_companyName_idx" ON "customer"("companyName");

ALTER TABLE "customer" ADD CONSTRAINT "customer_userId_fkey" FOREIGN KEY ("userId") REFERENCES "user"("id") ON DELETE SET NULL ON UPDATE CASCADE;
