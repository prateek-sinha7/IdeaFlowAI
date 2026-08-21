"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { getToken } from "@/lib/api";
import { routes } from "@/lib/routes";

export default function Home() {
  const router = useRouter();

  useEffect(() => {
    const token = getToken();
    if (token) {
      router.replace(routes.home());
    } else {
      router.replace(routes.login());
    }
  }, [router]);

  return null;
}
