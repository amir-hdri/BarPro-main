"use client";

import React, { useEffect, useRef, useState, useCallback } from "react";
import {
  PlateParts,
  parsePlateString,
  formatPlatePartsToString,
  normalizeDigits,
  mapEnglishKeyToPersianLetter,
  POPULAR_PLATE_LETTERS,
  ALL_PLATE_LETTERS,
} from "@/lib/plate";
import { toPersianDigits } from "@/lib/format";
import { ChevronDown, Check } from "lucide-react";

export { parsePlateString };

interface PlateInputProps {
  value?: string;
  onChange: (value: string) => void;
  error?: string;
  className?: string;
  autoFocus?: boolean;
}

export const PlateInput: React.FC<PlateInputProps> = ({
  value = "",
  onChange,
  error,
  className,
  autoFocus,
}) => {
  const [parts, setParts] = useState<PlateParts>(() => parsePlateString(value));
  const [isLetterMenuOpen, setIsLetterMenuOpen] = useState(false);
  const letterMenuRef = useRef<HTMLDivElement>(null);

  // همگام‌سازی state داخلی با prop value ورودی
  useEffect(() => {
    const nextParts = parsePlateString(value);
    setParts((prev) => {
      if (
        prev.part1 === nextParts.part1 &&
        prev.part2 === nextParts.part2 &&
        prev.part3 === nextParts.part3 &&
        prev.part4 === nextParts.part4
      ) {
        return prev;
      }
      return nextParts;
    });
  }, [value]);

  // بستن منوی حروف با کلیک بیرون از آن
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (letterMenuRef.current && !letterMenuRef.current.contains(event.target as Node)) {
        setIsLetterMenuOpen(false);
      }
    }
    if (isLetterMenuOpen) {
      document.addEventListener("mousedown", handleClickOutside);
      return () => document.removeEventListener("mousedown", handleClickOutside);
    }
  }, [isLetterMenuOpen]);

  const part1Ref = useRef<HTMLInputElement>(null);
  const part2Ref = useRef<HTMLInputElement>(null);
  const part3Ref = useRef<HTMLInputElement>(null);
  const part4Ref = useRef<HTMLInputElement>(null);

  const refs = [part1Ref, part2Ref, part3Ref, part4Ref];

  useEffect(() => {
    if (autoFocus && part1Ref.current) {
      part1Ref.current.focus();
    }
  }, [autoFocus]);

  const emitChange = useCallback(
    (newParts: PlateParts) => {
      setParts(newParts);
      const str = formatPlatePartsToString(newParts);
      onChange(str);
    },
    [onChange]
  );

  const handleSelectLetter = (letter: string) => {
    const newParts = { ...parts, part2: letter };
    emitChange(newParts);
    setIsLetterMenuOpen(false);
    // پرش هوشمند به بخش ۳ (سه رقم وسط) پس از انتخاب حرف
    setTimeout(() => {
      part3Ref.current?.focus();
      part3Ref.current?.select();
    }, 50);
  };

  const handleInputChange = (index: number, rawVal: string) => {
    let nextValue = normalizeDigits(rawVal);
    const newParts = { ...parts };

    if (index === 0) {
      // ۲ رقم اول سمت چپ
      nextValue = nextValue.replace(/\D/g, "");
      newParts.part1 = nextValue.slice(0, 2);
      emitChange(newParts);

      if (newParts.part1.length >= 2) {
        part2Ref.current?.focus();
        part2Ref.current?.select();
      }
    } else if (index === 1) {
      // حرف میانی
      // تبدیل احتمالی کلید انگلیسی به فارسی
      if (nextValue.length > 0) {
        const lastChar = nextValue.slice(-1);
        const mapped = mapEnglishKeyToPersianLetter(lastChar);
        if (nextValue.length === 1) {
          nextValue = mapped;
        } else if (nextValue === "ال" || nextValue === "الف") {
          // مجاز
        } else {
          nextValue = mapped;
        }
      }

      if (nextValue === "الف" || nextValue === "ال" || nextValue === "ا") {
        newParts.part2 = nextValue;
      } else {
        newParts.part2 = nextValue.slice(0, 1);
      }
      emitChange(newParts);

      const isCompletedLetter =
        newParts.part2 === "الف" || (newParts.part2.length === 1 && newParts.part2 !== "ا");

      if (isCompletedLetter) {
        part3Ref.current?.focus();
        part3Ref.current?.select();
      }
    } else if (index === 2) {
      // ۳ رقم وسط
      nextValue = nextValue.replace(/\D/g, "");
      newParts.part3 = nextValue.slice(0, 3);
      emitChange(newParts);

      if (newParts.part3.length >= 3) {
        part4Ref.current?.focus();
        part4Ref.current?.select();
      }
    } else if (index === 3) {
      // ۲ رقم کد شهر (ایران)
      nextValue = nextValue.replace(/\D/g, "");
      newParts.part4 = nextValue.slice(0, 2);
      emitChange(newParts);
    }
  };

  const handleKeyDown = (index: number, e: React.KeyboardEvent<HTMLInputElement>) => {
    // جابجایی با Backspace به فیلد قبلی
    if (e.key === "Backspace") {
      const currentPartValue = parts[`part${index + 1}` as keyof PlateParts];
      if (currentPartValue === "" && index > 0) {
        e.preventDefault();
        const prevRef = refs[index - 1].current;
        prevRef?.focus();
        prevRef?.select();
      }
    }

    // ناوبری هوشمند با کلیدهای چپ و راست
    if (e.key === "ArrowRight" && index < 3) {
      const input = refs[index].current;
      if (input && input.selectionEnd === input.value.length) {
        e.preventDefault();
        const nextRef = refs[index + 1].current;
        nextRef?.focus();
        nextRef?.select();
      }
    } else if (e.key === "ArrowLeft" && index > 0) {
      const input = refs[index].current;
      if (input && input.selectionStart === 0) {
        e.preventDefault();
        const prevRef = refs[index - 1].current;
        prevRef?.focus();
        prevRef?.select();
      }
    }
  };

  const handlePaste = (e: React.ClipboardEvent) => {
    const pasteData = e.clipboardData.getData("text");
    if (pasteData) {
      const parsed = parsePlateString(pasteData);
      if (parsed.part1 || parsed.part2 || parsed.part3 || parsed.part4) {
        e.preventDefault();
        emitChange(parsed);
      }
    }
  };

  return (
    <div className={`flex flex-col gap-2 relative ${className || ""}`} onPaste={handlePaste}>
      {/* فریم فیزیکی پلاک خودرو ایران */}
      <div
        className={`flex items-stretch h-14 bg-white border-[3px] ${
          error
            ? "border-rose-500 ring-2 ring-rose-500/20"
            : "border-slate-900 focus-within:ring-4 focus-within:ring-cyan-500/25 focus-within:border-cyan-600"
        } rounded-2xl overflow-visible shadow-xl transition-all dir-ltr relative select-none`}
      >
        {/* نوار پرچم و عبارت I.R. IRAN در سمت چپ */}
        <div className="w-10 bg-cyan-900 flex flex-col items-center justify-end pb-1.5 relative select-none shrink-0 rounded-l-[13px] overflow-hidden">
          <div className="absolute top-0 left-0 w-full h-[4px] bg-emerald-600"></div>
          <div className="absolute top-[4px] left-0 w-full h-[4px] bg-white"></div>
          <div className="absolute top-[8px] left-0 w-full h-[4px] bg-rose-600"></div>
          <span className="text-[8px] font-black text-white leading-none tracking-tighter">I.R.</span>
          <span className="text-[7.5px] font-black text-white leading-none mt-1 tracking-tighter">IRAN</span>
        </div>

        {/* بخش ۱: ۲ رقم سمت چپ */}
        <input
          ref={part1Ref}
          type="text"
          inputMode="numeric"
          className="w-12 text-center text-xl font-black bg-transparent border-r border-slate-200 outline-none text-slate-950 placeholder:text-slate-300 font-sans transition-colors"
          value={toPersianDigits(parts.part1)}
          onChange={(e) => handleInputChange(0, e.target.value)}
          onKeyDown={(e) => handleKeyDown(0, e)}
          onFocus={(e) => e.target.select()}
          maxLength={2}
          placeholder="--"
          aria-label="دو رقم اول پلاک"
        />

        {/* بخش ۲: حرف میانی با کلید انتخاب سریع */}
        <div className="relative flex items-center" ref={letterMenuRef}>
          <input
            ref={part2Ref}
            type="text"
            className="w-14 text-center text-xl font-black bg-transparent border-r border-slate-200 outline-none text-slate-950 placeholder:text-slate-300 font-sans dir-rtl"
            value={parts.part2}
            onChange={(e) => handleInputChange(1, e.target.value)}
            onKeyDown={(e) => handleKeyDown(1, e)}
            onFocus={(e) => e.target.select()}
            maxLength={parts.part2.startsWith("ا") ? 3 : 1}
            placeholder="حرف"
            aria-label="حرف میانی پلاک"
          />

          <button
            type="button"
            onClick={() => setIsLetterMenuOpen((prev) => !prev)}
            className="absolute left-1 h-5 w-4 flex items-center justify-center text-slate-400 hover:text-cyan-700 transition"
            title="انتخاب سریع حرف پلاک"
            aria-label="انتخاب سریع حرف پلاک"
            aria-expanded={isLetterMenuOpen}
            tabIndex={-1}
          >
            <ChevronDown className="h-3.5 w-3.5" />
          </button>

          {/* منوی بازشوی انتخاب سریع حروف */}
          {isLetterMenuOpen && (
            <div className="absolute top-full mt-2 left-1/2 -translate-x-1/2 z-50 w-64 rounded-2xl bg-slate-950 border border-cyan-500/30 p-3 shadow-2xl backdrop-blur-xl animate-in fade-in zoom-in-95 duration-150 dir-rtl text-white">
              <div className="mb-2 pb-1.5 border-b border-white/10 flex items-center justify-between">
                <span className="text-[11px] font-bold text-cyan-400">حروف پرکاربرد ترابری و باری:</span>
              </div>
              <div className="grid grid-cols-2 gap-1.5 mb-3">
                {POPULAR_PLATE_LETTERS.map((item) => (
                  <button
                    key={item.letter}
                    type="button"
                    onClick={() => handleSelectLetter(item.letter)}
                    className={`flex items-center justify-between px-2.5 py-1.5 rounded-xl text-xs font-bold transition ${
                      parts.part2 === item.letter
                        ? "bg-cyan-500 text-slate-950"
                        : "bg-white/5 text-slate-200 hover:bg-cyan-500/20 hover:text-cyan-300"
                    }`}
                  >
                    <span>{item.label}</span>
                    {parts.part2 === item.letter && <Check className="h-3 w-3" />}
                  </button>
                ))}
              </div>

              <div className="mb-1.5 text-[10px] text-slate-400 font-semibold">سایر حروف:</div>
              <div className="grid grid-cols-6 gap-1 max-h-32 overflow-y-auto custom-scrollbar">
                {ALL_PLATE_LETTERS.filter((l) => !POPULAR_PLATE_LETTERS.some((p) => p.letter === l)).map((l) => (
                  <button
                    key={l}
                    type="button"
                    onClick={() => handleSelectLetter(l)}
                    className={`h-7 rounded-lg text-xs font-black transition ${
                      parts.part2 === l
                        ? "bg-cyan-500 text-slate-950"
                        : "bg-white/5 text-slate-300 hover:bg-white/15 hover:text-white"
                    }`}
                  >
                    {l}
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* بخش ۳: ۳ رقم وسط */}
        <input
          ref={part3Ref}
          type="text"
          inputMode="numeric"
          className="w-16 text-center text-xl font-black bg-transparent border-r-2 border-slate-950 outline-none text-slate-950 placeholder:text-slate-300 font-sans"
          value={toPersianDigits(parts.part3)}
          onChange={(e) => handleInputChange(2, e.target.value)}
          onKeyDown={(e) => handleKeyDown(2, e)}
          onFocus={(e) => e.target.select()}
          maxLength={3}
          placeholder="---"
          aria-label="سه رقم وسط پلاک"
        />

        {/* بخش ۴: کادر ایران و ۲ رقم کد شهر سمت راست */}
        <div className="flex flex-col flex-1 min-w-[50px] items-center justify-center bg-transparent relative rounded-r-[13px]">
          <span className="text-[9px] font-black text-slate-800 absolute top-1 font-sans select-none tracking-tight">
            ایران
          </span>
          <input
            ref={part4Ref}
            type="text"
            inputMode="numeric"
            className="w-full text-center text-xl font-black bg-transparent outline-none text-slate-950 placeholder:text-slate-300 mt-2.5 font-sans"
            value={toPersianDigits(parts.part4)}
            onChange={(e) => handleInputChange(3, e.target.value)}
            onKeyDown={(e) => handleKeyDown(3, e)}
            onFocus={(e) => e.target.select()}
            maxLength={2}
            placeholder="--"
            aria-label="دو رقم کد ایران پلاک"
          />
        </div>
      </div>

      {/* چیپ‌های انتخاب فوق سریع حروف پرکاربرد در زیر اینپوت */}
      <div className="flex items-center gap-1.5 flex-wrap pt-0.5 dir-rtl">
        <span className="text-[11px] font-medium text-slate-400 ml-1 select-none">انتخاب سریع:</span>
        {POPULAR_PLATE_LETTERS.map((item) => (
          <button
            key={item.letter}
            type="button"
            onClick={() => handleSelectLetter(item.letter)}
            className={`px-2 py-0.5 rounded-lg text-[11px] font-bold transition-all active:scale-95 ${
              parts.part2 === item.letter
                ? "bg-cyan-500 text-slate-950 shadow-sm shadow-cyan-500/40"
                : item.isTruck
                ? "bg-cyan-500/10 text-cyan-300 border border-cyan-500/20 hover:bg-cyan-500/20"
                : "bg-white/5 text-slate-400 border border-white/5 hover:bg-white/10 hover:text-slate-200"
            }`}
          >
            {item.letter === "ع" ? "ع (باری)" : item.letter === "ت" ? "ت (ترانزیت)" : item.letter}
          </button>
        ))}
      </div>

      {error && <p className="text-xs text-rose-400 font-bold dir-rtl">{error}</p>}
    </div>
  );
};


