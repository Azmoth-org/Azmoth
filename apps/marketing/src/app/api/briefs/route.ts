import { NextRequest, NextResponse } from "next/server";
import { auth } from "@/lib/auth";
import prisma from "@/lib/prisma";
import { notifyBriefSubmitted } from "@/lib/email";
import { createNotification } from "@/lib/notifications";

/**
 * POST /api/briefs
 * Saves a project brief to the database, linked to the current session
 * (anonymous or registered user).
 */
export async function POST(request: NextRequest) {
  try {
    const session = await auth.api.getSession({ headers: request.headers });
    if (!session?.user?.id) {
      return NextResponse.json(
        { error: "No active session — sign in anonymously first." },
        { status: 401 }
      );
    }

    const body = await request.json();
    const {
      name,
      company,
      email,
      phone,
      category,
      description,
      budget,
      timeline,
      ref,
      conversation,
    } = body ?? {};

    if (!category || !description) {
      return NextResponse.json(
        { error: "category and description are required" },
        { status: 400 }
      );
    }

    const brief = await prisma.brief.create({
      data: {
        userId: session.user.id,
        name: name || null,
        email: email || null,
        category: category || null,
        description: description || null,
        scope: JSON.stringify({
          company: company || null,
          phone: phone || null,
          budget: budget || null,
          timeline: timeline || null,
          ref: ref || null,
          conversation: conversation || [],
        }),
        status: "received",
      },
    });

    // In-app notification for the portal user
    void createNotification({
      userId: session.user.id,
      type: "brief",
      title: "Brief received",
      body: `We received your brief${ref ? " " + ref : ""} — our team will review it and get back to you within 24 hours.`,
      href: "/dashboard",
    });

    // Fire the transactional emails (studio notification + client
    // confirmation) — non-blocking; brief already saved.
    const finalRef = ref || brief.id;
    void notifyBriefSubmitted({
      ref: finalRef,
      name,
      company,
      email,
      phone,
      category,
      budget,
      timeline,
      description,
    });

    return NextResponse.json({ ok: true, id: brief.id, ref: finalRef });
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : String(err);
    return NextResponse.json({ ok: false, error: message }, { status: 500 });
  }
}
