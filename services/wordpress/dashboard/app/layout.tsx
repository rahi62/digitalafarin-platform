import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = { title: "WP Agent | DigitalAfarin", description: "مدیریت هوشمند سایت‌های وردپرسی دیجیتال آفرین" };

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="fa" dir="rtl"><body>{children}</body></html>;
}
