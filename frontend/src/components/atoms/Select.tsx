import {
  Children,
  isValidElement,
  useId,
  useLayoutEffect,
  useRef,
  useState,
  type SelectHTMLAttributes,
  type ReactNode,
  type ChangeEvent,
} from "react";
import { createPortal } from "react-dom";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
type Choice = { value: string; label: string; disabled: boolean };
function text(node: ReactNode): string {
  return Children.toArray(node)
    .map((c) =>
      isValidElement(c) ? text((c.props as any).children) : String(c),
    )
    .join("");
}
function choices(node: ReactNode): Choice[] {
  return Children.toArray(node).flatMap((c) => {
    if (!isValidElement(c)) return [];
    const p = c.props as any;
    return c.type === "option"
      ? [
          {
            value: String(p.value ?? text(p.children)),
            label: text(p.children),
            disabled: !!p.disabled,
          },
        ]
      : choices(p.children);
  });
}
export default function Select({
  children,
  onChange,
  value,
  defaultValue,
  multiple,
  id,
  ...props
}: SelectHTMLAttributes<HTMLSelectElement>) {
  const uid = useId().replaceAll(":", "");
  const native = useRef<HTMLSelectElement>(null),
    trigger = useRef<HTMLButtonElement>(null),
    list = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false),
    [index, setIndex] = useState(0),
    [label, setLabel] = useState(String(props["aria-label"] || "Pilihan")),
    [position, setPosition] = useState({
      left: 0,
      top: 0,
      width: 200,
      maxHeight: 280,
    });
  const reduced = useReducedMotion();
  const items = choices(children),
    values = (
      Array.isArray(value)
        ? value
        : [value ?? defaultValue ?? (multiple ? undefined : items[0]?.value)]
    )
      .filter((v) => v !== undefined)
      .map(String);
  const selected = items.filter((o) => values.includes(o.value));
  const locate = () => {
    const box = trigger.current?.getBoundingClientRect();
    if (!box) return;
    const available = innerHeight - box.bottom - 16;
    const maxHeight = Math.max(
      110,
      Math.min(280, available < 150 ? box.top - 16 : available),
    );
    setPosition({
      left: Math.max(10, Math.min(box.left, innerWidth - box.width - 10)),
      top:
        available < 150
          ? Math.max(10, box.top - maxHeight - 7)
          : box.bottom + 7,
      width: Math.min(Math.max(box.width, 200), innerWidth - 20),
      maxHeight,
    });
  };
  useLayoutEffect(() => {
    const n = native.current;
    const l = n?.labels?.[0];
    if (props["aria-label"]) setLabel(String(props["aria-label"]));
    else if (l) {
      const content = Array.from(l.childNodes)
        .filter((x) => x.nodeType === Node.TEXT_NODE)
        .map((x) => x.textContent)
        .join("")
        .trim();
      setLabel(content || l.textContent?.trim() || "Pilihan");
    }
    if (!l) return;
    const focus = (e: MouseEvent) => {
      if (e.target === l) {
        e.preventDefault();
        trigger.current?.focus();
      }
    };
    l.addEventListener("click", focus);
    return () => l.removeEventListener("click", focus);
  }, [children, props["aria-label"]]);
  useLayoutEffect(() => {
    if (!open) return;
    locate();
    const outside = (e: PointerEvent) => {
      if (
        !trigger.current?.contains(e.target as Node) &&
        !list.current?.contains(e.target as Node)
      )
        setOpen(false);
    };
    window.addEventListener("pointerdown", outside);
    window.addEventListener("resize", locate);
    window.addEventListener("scroll", locate, true);
    return () => {
      window.removeEventListener("pointerdown", outside);
      window.removeEventListener("resize", locate);
      window.removeEventListener("scroll", locate, true);
    };
  }, [open]);
  useLayoutEffect(() => {
    if (open)
      document
        .getElementById(`${uid}-${index}`)
        ?.scrollIntoView({ block: "nearest" });
  }, [index, open]);
  const choose = (i: number) => {
    if (items[i]?.disabled || !native.current) return;
    const item = items[i],
      next = multiple
        ? values.includes(item.value)
          ? values.filter((v) => v !== item.value)
          : [...values, item.value]
        : [item.value];
    for (const option of native.current.options)
      option.selected = next.includes(option.value);
    onChange?.({
      target: native.current,
      currentTarget: native.current,
    } as ChangeEvent<HTMLSelectElement>);
    if (!multiple) setOpen(false);
    trigger.current?.focus({ preventScroll: true });
  };
  const expand = () => {
    locate();
    setIndex(Math.max(0, items.findIndex(item => values.includes(item.value) && !item.disabled)));
    setOpen(true);
  };
  const move = (direction: number) => {
    let i = index;
    for (let tries = 0; tries < items.length; tries++) {
      i = (i + direction + items.length) % items.length;
      if (!items[i].disabled) {
        setIndex(i);
        return;
      }
    }
  };
  return (
    <span className={`custom-select ${props.className || ""}`}>
      <select
        {...props}
        id={id}
        ref={native}
        className="select-native"
        aria-hidden="true"
        tabIndex={-1}
        value={value}
        defaultValue={defaultValue}
        multiple={multiple}
        onChange={onChange}
      >
        {children}
      </select>
      <button
        ref={trigger}
        type="button"
        role="combobox"
        aria-label={label}
        aria-expanded={open}
        aria-haspopup="listbox"
        aria-controls={open ? uid : undefined}
        aria-activedescendant={open ? `${uid}-${index}` : undefined}
        aria-required={props.required || undefined}
        disabled={props.disabled}
        className="select-trigger"
        onClick={() => {
          locate();
          setIndex(
            Math.max(
              0,
              items.findIndex((i) => values.includes(i.value)),
            ),
          );
          setOpen((v) => !v);
        }}
        onKeyDown={(e) => {
          if (
            [
              "ArrowDown",
              "ArrowUp",
              "Home",
              "End",
              "Escape",
              "Enter",
              " ",
            ].includes(e.key)
          )
            e.preventDefault();
          if (e.key === "Escape") {
            setOpen(false);
            return;
          }
          if (e.key === "Tab") {
            setOpen(false);
            return;
          }
          if (e.key === "ArrowDown" || e.key === "ArrowUp") {
            if (!open) {
              expand();
            } else move(e.key === "ArrowDown" ? 1 : -1);
          } else if (e.key === "Home")
            setIndex(items.findIndex((i) => !i.disabled));
          else if (e.key === "End")
            setIndex(
              items.length -
                1 -
                [...items].reverse().findIndex((i) => !i.disabled),
            );
          else if (e.key === "Enter" || e.key === " ") {
            if (open) choose(index);
            else {
              expand();
            }
          } else if (e.key.length === 1) {
            const match = items.findIndex(
              (o) =>
                !o.disabled &&
                o.label
                  .toLocaleLowerCase()
                  .startsWith(e.key.toLocaleLowerCase()),
            );
            if (match >= 0) {
              setIndex(match);
              if (!open) {
                locate();
                setOpen(true);
              }
            }
          }
        }}
      >
        <span>
          {selected.length
            ? selected.map((i) => i.label).join(", ")
            : multiple
              ? "Pilih satu atau beberapa berkas"
              : "Pilih opsi"}
        </span>
        <svg viewBox="0 0 24 24" width="17" height="17" aria-hidden="true">
          <path
            d="m6 9 6 6 6-6"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.8"
          />
        </svg>
      </button>
      {createPortal(
        <AnimatePresence>
          {open && (
            <motion.div
              ref={list}
              key={uid}
              id={uid}
              className="select-popover"
              role="listbox"
              aria-label={label}
              aria-multiselectable={multiple || undefined}
              style={{ position: "fixed", ...position }}
              initial={{
                opacity: 0,
                y: reduced ? 0 : -5,
                scale: reduced ? 1 : 0.98,
              }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: reduced ? 0 : -4 }}
              transition={{ duration: reduced ? 0 : 0.15 }}
            >
              {items.length ? (
                items.map((item, i) => (
                  <div
                    id={`${uid}-${i}`}
                    key={item.value}
                    role="option"
                    aria-selected={values.includes(item.value)}
                    aria-disabled={item.disabled || undefined}
                    className={`select-option ${index === i ? "highlighted" : ""}`}
                    onPointerMove={() => setIndex(i)}
                    onPointerDown={(e) => e.preventDefault()}
                    onClick={() => choose(i)}
                  >
                    <span>{item.label}</span>
                    {values.includes(item.value) && (
                      <span className="select-check" aria-hidden="true">
                        ✓
                      </span>
                    )}
                  </div>
                ))
              ) : (
                <p className="select-empty">
                  Belum ada pilihan. Unggah berkas terlebih dahulu.
                </p>
              )}
            </motion.div>
          )}
        </AnimatePresence>,
        document.body,
      )}
    </span>
  );
}
