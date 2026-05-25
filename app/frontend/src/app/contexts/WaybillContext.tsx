"use client";

import { createContext, useContext, useReducer, ReactNode } from "react";

export type NavTab =
  | "waybill-form"
  | "manual-entry"
  | "excel-upload"
  | "map-tools"
  | "reports-tools"
  | "management-tools";

export type RequestState = "idle" | "loading" | "success" | "error";

export interface WaybillFormData {
  senderName: string;
  senderPhone: string;
  senderAddress: string;
  senderNationalCode: string;
  receiverName: string;
  receiverPhone: string;
  receiverAddress: string;
  receiverNationalCode: string;
  originProvince: string;
  originCity: string;
  originDistrict: string;
  originAddress: string;
  destinationProvince: string;
  destinationCity: string;
  destinationDistrict: string;
  destinationAddress: string;
  cargoType: string;
  cargoWeight: string;
  cargoCount: string;
  cargoDescription: string;
  vehiclePlate: string;
  vehicleType: string;
  driverNationalCode: string;
  driverPhone: string;
  financialCost: string;
  paymentMethod: string;
  operationMode: "safe" | "full";
  twoWay: boolean;
  timeLimit: string;
  notes: string;
}

interface WaybillState {
  formData: WaybillFormData;
  activeTab: NavTab;
  darkMode: boolean;
  sidebarOpen: boolean;
  submitState: RequestState;
  uploadState: RequestState;
  submitMessage: string;
  uploadMessage: string;
  apiKey: string;
}

type WaybillAction =
  | { type: "SET_FORM_DATA"; payload: Partial<WaybillFormData> }
  | { type: "RESET_FORM" }
  | { type: "SET_ACTIVE_TAB"; payload: NavTab }
  | { type: "TOGGLE_DARK_MODE" }
  | { type: "TOGGLE_SIDEBAR" }
  | { type: "SET_SUBMIT_STATE"; payload: RequestState }
  | { type: "SET_UPLOAD_STATE"; payload: RequestState }
  | { type: "SET_SUBMIT_MESSAGE"; payload: string }
  | { type: "SET_UPLOAD_MESSAGE"; payload: string }
  | { type: "SET_API_KEY"; payload: string };

const initialFormData: WaybillFormData = {
  senderName: "",
  senderPhone: "",
  senderAddress: "",
  senderNationalCode: "",
  receiverName: "",
  receiverPhone: "",
  receiverAddress: "",
  receiverNationalCode: "",
  originProvince: "",
  originCity: "",
  originDistrict: "",
  originAddress: "",
  destinationProvince: "",
  destinationCity: "",
  destinationDistrict: "",
  destinationAddress: "",
  cargoType: "",
  cargoWeight: "",
  cargoCount: "1",
  cargoDescription: "",
  vehiclePlate: "",
  vehicleType: "",
  driverNationalCode: "",
  driverPhone: "",
  financialCost: "",
  paymentMethod: "",
  operationMode: "safe",
  twoWay: false,
  timeLimit: "",
  notes: "",
};

const initialState: WaybillState = {
  formData: initialFormData,
  activeTab: "waybill-form",
  darkMode: false,
  sidebarOpen: true,
  submitState: "idle",
  uploadState: "idle",
  submitMessage: "",
  uploadMessage: "",
  apiKey: "",
};

function waybillReducer(state: WaybillState, action: WaybillAction): WaybillState {
  switch (action.type) {
    case "SET_FORM_DATA":
      return { ...state, formData: { ...state.formData, ...action.payload } };
    case "RESET_FORM":
      return { ...state, formData: initialFormData, submitState: "idle", submitMessage: "" };
    case "SET_ACTIVE_TAB":
      return { ...state, activeTab: action.payload };
    case "TOGGLE_DARK_MODE":
      return { ...state, darkMode: !state.darkMode };
    case "TOGGLE_SIDEBAR":
      return { ...state, sidebarOpen: !state.sidebarOpen };
    case "SET_SUBMIT_STATE":
      return { ...state, submitState: action.payload };
    case "SET_UPLOAD_STATE":
      return { ...state, uploadState: action.payload };
    case "SET_SUBMIT_MESSAGE":
      return { ...state, submitMessage: action.payload };
    case "SET_UPLOAD_MESSAGE":
      return { ...state, uploadMessage: action.payload };
    case "SET_API_KEY":
      return { ...state, apiKey: action.payload };
    default:
      return state;
  }
}

interface WaybillContextType {
  state: WaybillState;
  dispatch: React.Dispatch<WaybillAction>;
}

const WaybillContext = createContext<WaybillContextType | undefined>(undefined);

export function WaybillProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(waybillReducer, initialState);
  return (
    <WaybillContext.Provider value={{ state, dispatch }}>
      {children}
    </WaybillContext.Provider>
  );
}

export function useWaybill() {
  const context = useContext(WaybillContext);
  if (!context) {
    throw new Error("useWaybill must be used within WaybillProvider");
  }
  return context;
}
