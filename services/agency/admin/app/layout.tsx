import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: {
    default: "پنل مدیریت دیجیتال‌آفرین",
    template: "%s | دیجیتال‌آفرین",
  },
  description: "مرکز کنترل عملیاتی DigitalAfarin Agency",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="fa" dir="rtl">
      <body>{children}</body>
    </html>
  );
}
