import { redirect } from "next/navigation";
import { env } from "@/config/env";
export default function HomePage() { redirect(env.pilotModeEnabled ? "/monitor" : "/command-center"); }
