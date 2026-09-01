import { NextResponse } from "next/server";
import { syncServer } from "@/lib/api";

export async function POST() {
  try {
    const response = await syncServer();
    const body = await response.json().catch(() => ({ detail: "Invalid API response" }));
    return NextResponse.json(body, { status: response.status });
  } catch (error) {
    const detail = error instanceof Error ? error.message : "Sync failed";
    return NextResponse.json({ detail }, { status: 500 });
  }
}
