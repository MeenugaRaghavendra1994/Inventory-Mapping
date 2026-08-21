import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Inventory Mapping API",
  description: "Inventory Mapping backend service",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
