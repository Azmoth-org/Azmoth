import { betterAuth } from "better-auth";
import { prismaAdapter } from "better-auth/adapters/prisma";
import { anonymous, admin, magicLink } from "better-auth/plugins";
import prisma from "@/lib/prisma";
import type { Prisma } from "@prisma/client";
import { generateUniqueSlug } from "@/lib/slug";
import { sendEmail } from "@/lib/email";
import {
  resetPasswordTemplate,
  verifyEmailTemplate,
  magicLinkTemplate,
} from "@/lib/emailTemplates";

const ADMIN_EMAILS = (process.env.ADMIN_EMAILS || "")
  .split(",")
  .map((e) => e.trim().toLowerCase())
  .filter(Boolean);

export const auth = betterAuth({
  database: prismaAdapter(prisma, {
    provider: "postgresql",
  }),
  user: {
    // Expose the client-portal slug in session user payloads (sidebar links).
    additionalFields: {
      slug: { type: "string", required: false },
    },
  },
  socialProviders: {
    google: {
      clientId: process.env.GOOGLE_CLIENT_ID || "",
      clientSecret: process.env.GOOGLE_CLIENT_SECRET || "",
    },
    linkedin: {
      clientId: process.env.LINKEDIN_CLIENT_ID || "",
      clientSecret: process.env.LINKEDIN_CLIENT_SECRET || "",
    },
  },
  emailAndPassword: {
    enabled: true,
    sendResetPassword: async ({ user, url }) => {
      await sendEmail({
        to: user.email,
        subject: "Reset your SILKDEV password",
        html: resetPasswordTemplate({ url }),
      });
    },
  },
  emailVerification: {
    sendVerificationEmail: async ({ user, url }) => {
      await sendEmail({
        to: user.email,
        subject: "Verify your SILKDEV email",
        html: verifyEmailTemplate({ url }),
      });
    },
  },
  // Auto-promote studio emails to admin — on signup (create) and on every
  // sign-in (session create), so role grants self-heal for existing users
  // whose email was added to ADMIN_EMAILS after their account was created.
  databaseHooks: {
    user: {
      create: {
        after: async (user) => {
          const data: Prisma.UserUpdateInput = {};
          if (ADMIN_EMAILS.includes(user.email.toLowerCase())) {
            data.role = "admin";
          }
          // Every account gets a stable client-portal slug (/client/{slug}).
          if (!user.slug) {
            data.slug = await generateUniqueSlug(user.email, user.name);
          }
          if (Object.keys(data).length > 0) {
            await prisma.user.update({ where: { id: user.id }, data });
          }
        },
      },
    },
    session: {
      create: {
        after: async (session) => {
          const user = await prisma.user.findUnique({
            where: { id: session.userId },
            select: { id: true, email: true, role: true },
          });
          if (user && user.role !== "admin" && ADMIN_EMAILS.includes(user.email.toLowerCase())) {
            await prisma.user.update({
              where: { id: user.id },
              data: { role: "admin" },
            });
          }
        },
      },
    },
  },
  plugins: [
    anonymous(),
    admin({
      defaultRole: "user",
      adminRoles: ["admin"],
    }),
    magicLink({
      sendMagicLink: async ({ email, url }) => {
        await sendEmail({
          to: email,
          subject: "Sign in to SILKDEV",
          html: magicLinkTemplate({ url }),
        });
      },
    }),
  ],
  trustedOrigins: [process.env.NEXT_PUBLIC_APP_URL || "http://localhost:3000"],
});
