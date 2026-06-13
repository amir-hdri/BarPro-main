"use client";

import React, { useEffect, useRef, useState } from "react";
import { normalizeDigits } from "@/lib/plate";

interface PlateInputProps {
  value: string;
  onChange: (value: string) => void;
  error?: string;
  className?: string;
}


// Helper to convert English digits to Persian for display if needed, 
// but usually inputs are better kept as they are if inputmode is numeric.
// However, the user specifically asked for Persian digits in the display.
const toPersianDigits = (str: string) => {
  const id = ["0", "1", "2", "3", "4", "5", "6", "7", "8", "9"];
  const fa = ["۰", "۱", "۲", "۳", "۴", "۵", "۶", "۷", "۸", "۹"];
  return str.replace(/[0-9]/g, (w) => fa[id.indexOf(w)]);
};

export const PlateInput: React.FC<PlateInputProps> = ({ value, onChange, error, className }) => {
  const parseValue = (val: string) => {
    // Expected format: 12ب345ایران67
    // We normalize digits to English for internal processing
    const normalized = normalizeDigits(val);
    const match = normalized.match(/^(\d{0,2})([^\d]*)(\d{0,3})(?:ایران)?(\d{0,2})$/u);
    
    if (match) {
      return {
        part1: match[1] || "",
        part2: (match[2] || "").replace("ایران", ""),
        part3: match[3] || "",
        part4: match[4] || "",
      };
    }
    return { part1: "", part2: "", part3: "", part4: "" };
  };

  const [parts, setParts] = useState(parseValue(value));

  // Update internal state when external value changes
  useEffect(() => {
    const nextParts = parseValue(value);
    if (JSON.stringify(nextParts) !== JSON.stringify(parts)) {
      setParts(nextParts);
    }
  }, [value, parts]);

  const part1Ref = useRef<HTMLInputElement>(null);
  const part2Ref = useRef<HTMLInputElement>(null);
  const part3Ref = useRef<HTMLInputElement>(null);
  const part4Ref = useRef<HTMLInputElement>(null);

  const refs = [part1Ref, part2Ref, part3Ref, part4Ref];

  const updateParts = (newParts: typeof parts) => {
    setParts(newParts);
    const { part1, part2, part3, part4 } = newParts;
    // We emit the format expected by the backend: 12ب345ایران67
    const fullPlate = `${part1}${part2}${part3}ایران${part4}`;
    onChange(fullPlate);
  };

  const handleInputChange = (index: number, val: string) => {
    let nextValue = normalizeDigits(val);
    const newParts = { ...parts };

    if (index === 0 || index === 2 || index === 3) {
      // Numeric fields: allow only digits
      nextValue = nextValue.replace(/[^\d]/g, "");
    } else {
      // Letter field: allow Persian letters
      nextValue = nextValue.replace(/[^\u0600-\u06FF]/g, "");
    }

    if (index === 0) newParts.part1 = nextValue.slice(0, 2);
    if (index === 1) {
      // Allow 'الف' as a multi-character plate letter step-by-step
      const allowedPrefixes = ["ا", "ال", "الف"];
      if (allowedPrefixes.includes(nextValue)) {
        newParts.part2 = nextValue;
      } else {
        newParts.part2 = nextValue.slice(0, 1);
      }
    }
    if (index === 2) newParts.part3 = nextValue.slice(0, 3);
    if (index === 3) newParts.part4 = nextValue.slice(0, 2);

    updateParts(newParts);

    // Auto-tab logic supporting multi-character 'الف' letter
    let shouldTab = false;
    if (index === 0) shouldTab = nextValue.length >= 2;
    else if (index === 1) {
      shouldTab = newParts.part2 === "الف" || (newParts.part2.length === 1 && newParts.part2 !== "ا");
    }
    else if (index === 2) shouldTab = nextValue.length >= 3;

    if (shouldTab && index < 3) {
      refs[index + 1].current?.focus();
    }
  };

  const handleKeyDown = (index: number, e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Backspace" && parts[`part${index + 1}` as keyof typeof parts] === "" && index > 0) {
      refs[index - 1].current?.focus();
    }
  };

  return (
    <div className={`flex flex-col gap-2 ${className}`}>
      <div 
        className="flex items-stretch h-14 bg-white border-2 border-slate-900 rounded-xl overflow-hidden shadow-sm"
        style={{ direction: 'ltr' }}
      >
        {/* Blue Bar (Flag Area) */}
        <div className="w-8 bg-[#003399] flex flex-col items-center justify-end pb-1 relative">
           <div className="absolute top-0 left-0 w-full h-[3px] bg-emerald-600"></div>
           <div className="absolute top-[3px] left-0 w-full h-[3px] bg-white"></div>
           <div className="absolute top-[6px] left-0 w-full h-[3px] bg-rose-600"></div>
           <span className="text-[7px] font-bold text-white leading-none">I.R.</span>
           <span className="text-[7px] font-bold text-white leading-none mt-0.5">IRAN</span>
        </div>

        {/* Part 1 (2 digits) */}
        <input
          ref={part1Ref}
          type="text"
          inputMode="numeric"
          className="w-12 text-center text-xl font-bold border-r border-slate-200 outline-none text-slate-900 placeholder:text-slate-200"
          value={toPersianDigits(parts.part1)}
          onChange={(e) => handleInputChange(0, e.target.value)}
          onKeyDown={(e) => handleKeyDown(0, e)}
          maxLength={2}
          placeholder="--"
        />

        {/* Part 2 (Letter) */}
        <input
          ref={part2Ref}
          type="text"
          className="w-12 text-center text-2xl font-bold border-r border-slate-200 outline-none text-slate-900 placeholder:text-slate-200"
          value={parts.part2}
          onChange={(e) => handleInputChange(1, e.target.value)}
          onKeyDown={(e) => handleKeyDown(1, e)}
          maxLength={parts.part2.startsWith("ا") ? 3 : 1}
          placeholder="الف"
          style={{ direction: 'rtl' }}
        />

        {/* Part 3 (3 digits) */}
        <input
          ref={part3Ref}
          type="text"
          inputMode="numeric"
          className="w-16 text-center text-xl font-bold border-r-2 border-slate-900 outline-none text-slate-900 placeholder:text-slate-200"
          value={toPersianDigits(parts.part3)}
          onChange={(e) => handleInputChange(2, e.target.value)}
          onKeyDown={(e) => handleKeyDown(2, e)}
          maxLength={3}
          placeholder="---"
        />

        {/* Part 4 (City Code) */}
        <div className="flex flex-col flex-1 min-w-[50px] items-center justify-center bg-slate-50 relative">
          <span className="text-[9px] font-black text-slate-400 absolute top-1">ایران</span>
          <input
            ref={part4Ref}
            type="text"
            inputMode="numeric"
            className="w-full text-center text-xl font-bold bg-transparent outline-none text-slate-900 placeholder:text-slate-200 mt-2"
            value={toPersianDigits(parts.part4)}
            onChange={(e) => handleInputChange(3, e.target.value)}
            onKeyDown={(e) => handleKeyDown(3, e)}
            maxLength={2}
            placeholder="--"
          />
        </div>
      </div>
      {error && <p className="text-xs text-rose-600 font-medium">{error}</p>}
    </div>
  );
};
