import Image, { type ImageProps } from "next/image";

import { cn } from "@/utils/cn";

type BrandMarkProps = Omit<ImageProps, "alt" | "height" | "src" | "width"> & {
  compact?: boolean;
};

/**
 * Единая растровая марка MedSignal для header, sidebar и mobile navigation.
 */
export function BrandMark({ className, compact = false, ...props }: BrandMarkProps) {
  return (
    <Image
      aria-hidden="true"
      alt=""
      className={cn(compact ? "h-8 w-8" : "h-10 w-10", className)}
      height={48}
      {...props}
      src="/brand/medsignal-icon.png"
      width={48}
    />
  );
}
