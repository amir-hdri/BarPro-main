"use client";

import React, { useEffect, useRef, useState } from "react";
import { normalizeDigits } from "@/lib/plate";
import { toPersianDigits } from "@/lib/format";

interface PlateInputProps {
  value: string;
  onChange: (value: string) => void;
  error?: string;
  className?: string;
}

export const parsePlateString = (val: string) => {
  if (!val) return { part1: "", part2: "", part3: "", part4: "" };
  const normalized = normalizeDigits(val).trim().replace(/[\s\-_/\\.]+/g, "");
  
  // Format 1: 12الف345ایران67 or 12الف34567
  const match1 = normalized.match(/^(\d{2})([^\d]+)(\d{3})(?:ایران)?(\d{2})$/u);
  if (match1) {
    return {
      part1: match1[1],
      part2: match1[2].replace("ایران", "").trim(),
      part3: match1[3],
      part4: match1[4],
    };
  }

  // Format 2: General partial match
  const match2 = normalized.match(/^(\d{0,2})([^\d]*)(\d{0,3})(?:ایران)?(\d{0,2})$/u);
  if (match2) {
    return {
      part1: match2[1] || "",
      part2: (match2[2] || "").replace("ایران", "").trim(),
      part3: match2[3] || "",
      part4: match2[4] || "",
    };
  }

  return { part1: "", part2: "", part3: "", part4: "" };
};

export const PlateInput: React.FC<PlateInputProps> = ({ value, onChange, error, className }) => {
  const [parts, setParts] = useState(parsePlateString(value));

  useEffect(() => {
    const nextParts = parsePlateString(value);
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
    const fullPlate = `${part1}${part2}${part3}ایران${part4}`;
    onChange(fullPlate);
  };

  const handleInputChange = (index: number, val: string) => {
    let nextValue = normalizeDigits(val);
    const newParts = { ...parts };

    if (index === 0 || index === 2 || index === 3) {
      nextValue = nextValue.replace(/[^\d]/g, "");
    } else {
      nextValue = nextValue.replace(/[^\u0600-\u06FF]/g, "");
    }

    if (index === 0) newParts.part1 = nextValue.slice(0, 2);
    if (index === 1) {
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

  const handlePaste = (e: React.ClipboardEvent) => {
    const pasteData = e.clipboardData.getData("text");
    if (pasteData) {
      const parsed = parsePlateString(pasteData);
      if (parsed.part1 || parsed.part2 || parsed.part3 || parsed.part4) {
        e.preventDefault();
        updateParts(parsed);
      }
    }
  };

  return (
    <div className={`flex flex-col gap-2 ${className || ""}`} onPaste={handlePaste}>
       <div className={`flex items-stretch h-14 bg-white border-[3px] ${
         error ? "border-rose-500 ring-2 ring-rose-500/20" : "border-slate-900 focus-within:ring-4 focus-within:ring-cyan-500/20 focus-within:border-cyan-600"
       } rounded-2xl overflow-hidden shadow-lg font-sans transition-all dir-ltr`}>
         <div className="w-10 bg-cyan-800 flex flex-col items-center justify-end pb-2 relative select-none shrink-0">
            <div className="absolute top-0 left-0 w-full h-[4px] bg-emerald-600"></div>
            <div className="absolute top-[4px] left-0 w-full h-[4px] bg-white"></div>
            <div className="absolute top-[8px] left-0 w-full h-[4px] bg-rose-600"></div>
            <span className="text-[8px] font-black text-white leading-none">I.R.</span>
            <span className="text-[8px] font-black text-white leading-none mt-1">IRAN</span>
         </div>

        <input
          ref={part1Ref}
          type="text"
          inputMode="numeric"
          className="w-12 text-center text-xl font-black bg-transparent border-r border-slate-200 outline-none text-slate-950 placeholder:text-slate-300 font-sans"
          value={toPersianDigits(parts.part1)}
          onChange={(e) => handleInputChange(0, e.target.value)}
          onKeyDown={(e) => handleKeyDown(0, e)}
          maxLength={2}
          placeholder="--"
        />

        <input
          ref={part2Ref}
          type="text"
          className="w-12 text-center text-2xl font-black bg-transparent border-r border-slate-200 outline-none text-slate-950 placeholder:text-slate-300 font-sans dir-rtl"
          value={parts.part2}
          onChange={(e) => handleInputChange(1, e.target.value)}
          onKeyDown={(e) => handleKeyDown(1, e)}
          maxLength={parts.part2.startsWith("ا") ? 3 : 1}
          placeholder="الف"
        />

        <input
          ref={part3Ref}
          type="text"
          inputMode="numeric"
          className="w-16 text-center text-xl font-black bg-transparent border-r-2 border-slate-950 outline-none text-slate-950 placeholder:text-slate-300 font-sans"
          value={toPersianDigits(parts.part3)}
          onChange={(e) => handleInputChange(2, e.target.value)}
          onKeyDown={(e) => handleKeyDown(2, e)}
          maxLength={3}
          placeholder="---"
        />

        <div className="flex flex-col flex-1 min-w-[50px] items-center justify-center bg-transparent relative">
          <span className="text-[10px] font-black text-slate-800 absolute top-1 font-sans select-none">ایران</span>
          <input
            ref={part4Ref}
            type="text"
            inputMode="numeric"
            className="w-full text-center text-xl font-black bg-transparent outline-none text-slate-950 placeholder:text-slate-300 mt-2.5 font-sans"
            value={toPersianDigits(parts.part4)}
            onChange={(e) => handleInputChange(3, e.target.value)}
            onKeyDown={(e) => handleKeyDown(3, e)}
            maxLength={2}
            placeholder="--"
          />
        </div>
      </div>
      {error && <p className="text-xs text-rose-400 font-bold">{error}</p>}
    </div>
  );
};

