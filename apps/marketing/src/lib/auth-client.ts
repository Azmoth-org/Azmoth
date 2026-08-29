import { createAuthClient } from "better-auth/react";
import { anonymousClient, adminClient, magicLinkClient } from "better-auth/client/plugins";

export const authClient = createAuthClient({
  baseURL: process.env.NEXT_PUBLIC_APP_URL || "http://localhost:3000",
  plugins: [anonymousClient(), adminClient(), magicLinkClient()],
});

export const { signUp, signIn, signOut, useSession } = authClient;
