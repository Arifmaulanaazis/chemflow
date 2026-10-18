import {
  Children,
  cloneElement,
  isValidElement,
  useRef,
  useState,
  type DetailsHTMLAttributes,
} from "react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
export default function Disclosure({
  children,
  open: initialOpen,
  className,
  ...props
}: DetailsHTMLAttributes<HTMLDetailsElement>) {
  const [open, setOpen] = useState(!!initialOpen),
    [closing, setClosing] = useState(false);
  const root = useRef<HTMLDetailsElement>(null);
  const reduced = useReducedMotion();
  const all = Children.toArray(children);
  const summary = all.find(
    (c) => isValidElement(c) && c.type === "summary",
  ) as any;
  return (
    <details {...props} ref={root} className={className} open={open || closing}>
      {summary &&
        cloneElement(summary, {
          "aria-expanded": open,
          onClick: (event: MouseEvent) => {
            event.preventDefault();
            if (open) {
              setClosing(true);
              root.current?.querySelector("summary")?.focus();
            }
            setOpen((v) => !v);
          },
        })}
      <AnimatePresence initial={false} onExitComplete={() => setClosing(false)}>
        {open && (
          <motion.div
            key="content"
            className="disclosure-content"
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: reduced ? 0 : 0.22 }}
            style={{ overflow: "hidden" }}
          >
            {all.filter((c) => c !== summary)}
          </motion.div>
        )}
      </AnimatePresence>
    </details>
  );
}
