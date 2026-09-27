import type { SVGProps } from "react";

import { cn } from "@/utils/cn";

type BrandMarkProps = SVGProps<SVGSVGElement> & {
  compact?: boolean;
};

/**
 * Собственный знак MedSignal: медицинский крест образован четырьмя потоками,
 * сходящимися к единой точке принятия решений.
 */
export function BrandMark({ className, compact = false, ...props }: BrandMarkProps) {
  return (
    <svg
      aria-hidden="true"
      className={cn(compact ? "h-8 w-8" : "h-10 w-10", className)}
      fill="none"
      viewBox="0 0 48 48"
      xmlns="http://www.w3.org/2000/svg"
      {...props}
    >
      <rect width="48" height="48" rx="14" fill="currentColor" />
      <path
        d="M14 15.5h7.2c1.55 0 2.8 1.25 2.8 2.8V24m10-9v7.2A2.8 2.8 0 0 1 31.2 25H24m10 8h-7.2A2.8 2.8 0 0 1 24 30.2V25m-10 8v-7.2A2.8 2.8 0 0 1 16.8 23H24"
        stroke="white"
        strokeLinecap="round"
        strokeWidth="3.25"
      />
      <circle cx="24" cy="24" r="3.6" fill="#F4C95D" stroke="white" strokeWidth="1.5" />
      <circle cx="14" cy="15.5" r="2" fill="#8FE4DA" />
      <circle cx="34" cy="15" r="2" fill="#8FE4DA" />
      <circle cx="34" cy="33" r="2" fill="#8FE4DA" />
      <circle cx="14" cy="33" r="2" fill="#8FE4DA" />
    </svg>
  );
}
