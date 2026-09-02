import type { Metadata } from "next";
import { AppShell } from "@/components/AppShell";
import "./globals.css";

export const metadata: Metadata = {
  title: {
    default: "DigitalAfarin Platform",
    template: "%s · DigitalAfarin Platform",
  },
  description: "پنل مدیریت زیرساخت و VPSهای دیجیتال آفرین",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="fa" dir="rtl">
      <body><AppShell>{children}</AppShell></body>
    </html>
  );
}
