import {redirect} from "next/navigation";
export default function HomePage() { redirect(process.env.NEXT_PUBLIC_PILOT_MODE === "true" ? "/monitor" : "/command-center"); }
