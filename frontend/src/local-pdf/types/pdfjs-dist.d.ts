declare module "pdfjs-dist/build/pdf.mjs" {
  export interface PDFDocumentProxy {
    numPages: number;
    getPage(pageNumber: number): Promise<PDFPageProxy>;
  }

  export interface PDFPageProxy {
    getViewport(params: { scale: number }): PDFPageViewport;
    render(params: { canvasContext: CanvasRenderingContext2D; viewport: PDFPageViewport }): { promise: Promise<void> };
  }

  export interface PDFPageViewport {
    width: number;
    height: number;
  }

  export interface PDFDocumentLoadingTask {
    promise: Promise<PDFDocumentProxy>;
  }

  export function getDocument(params: {
    url: string;
    httpHeaders?: Record<string, string>;
    withCredentials?: boolean;
  }): PDFDocumentLoadingTask;

  export const GlobalWorkerOptions: {
    workerSrc?: string;
  };
}

declare module "pdfjs-dist/build/pdf.worker.mjs";
