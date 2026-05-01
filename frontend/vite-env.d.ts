/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_LOCAL_PDF_API_BASE?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
