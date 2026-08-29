-- AlterTable: project lifecycle phases + quote + payment status
ALTER TABLE "project" ADD COLUMN "phase" TEXT NOT NULL DEFAULT 'intake',
ADD COLUMN "quote" JSONB,
ADD COLUMN "paymentStatus" TEXT;

-- CreateTable: persisted project conversation messages
CREATE TABLE "message" (
    "id" TEXT NOT NULL,
    "projectId" TEXT NOT NULL,
    "role" TEXT NOT NULL,
    "senderName" TEXT,
    "senderAvatar" TEXT,
    "content" TEXT NOT NULL,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "message_pkey" PRIMARY KEY ("id")
);

-- CreateIndex
CREATE INDEX "message_projectId_idx" ON "message"("projectId");

-- AddForeignKey
ALTER TABLE "message" ADD CONSTRAINT "message_projectId_fkey" FOREIGN KEY ("projectId") REFERENCES "project"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- CreateTable: project payments (Konnect)
CREATE TABLE "payment" (
    "id" TEXT NOT NULL,
    "projectId" TEXT NOT NULL,
    "kind" TEXT NOT NULL DEFAULT 'deposit',
    "amount" DOUBLE PRECISION NOT NULL,
    "currency" TEXT NOT NULL DEFAULT 'TND',
    "status" TEXT NOT NULL DEFAULT 'pending',
    "paymentRef" TEXT,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "payment_pkey" PRIMARY KEY ("id")
);

-- CreateIndex
CREATE INDEX "payment_projectId_idx" ON "payment"("projectId");

-- AddForeignKey
ALTER TABLE "payment" ADD CONSTRAINT "payment_projectId_fkey" FOREIGN KEY ("projectId") REFERENCES "project"("id") ON DELETE CASCADE ON UPDATE CASCADE;
