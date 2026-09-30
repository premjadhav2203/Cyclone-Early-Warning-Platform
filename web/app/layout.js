import { Public_Sans } from "next/font/google";
import "./globals.css";

const font = Public_Sans({ subsets: ["latin"], weight: ["400", "600", "700"] });

export const metadata = { title: "Cyclone Early Warning" };

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body className={font.className}>{children}</body>
    </html>
  );
}
