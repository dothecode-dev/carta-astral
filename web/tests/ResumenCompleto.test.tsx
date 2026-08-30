import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ResumenCompleto } from "@/components/ResumenCompleto";
import { getDict } from "@/lib/i18n";

const dict = getDict("es");

// Ocho secciones tal como las devuelve `GET /informe/indice/`: la primera sin
// generar todavía (parrafo vacío, restante = objetivo de palabras de la
// sección "firma", 900 en el catálogo real) y una ya generada, para cubrir
// las dos formas que puede tener la respuesta sin ramificar por eso.
const ochoSecciones = [
  { slug: "firma", titulo: "Tu firma", parrafo: "", restante: 900 },
  { slug: "mente", titulo: "Tu mente", parrafo: "Mercurio en tu carta habla de...", restante: 650 },
  { slug: "afectos", titulo: "Afectos y vínculos", parrafo: "", restante: 890 },
  { slug: "trabajo", titulo: "Vocación y trabajo", parrafo: "", restante: 800 },
  { slug: "tensiones", titulo: "Tensiones y aprendizajes", parrafo: "", restante: 1000 },
  { slug: "lentos", titulo: "Los planetas lentos", parrafo: "", restante: 800 },
  { slug: "casas", titulo: "Dónde se juega tu vida", parrafo: "", restante: 600 },
  { slug: "sintesis", titulo: "Síntesis", parrafo: "", restante: 700 },
];

describe("ResumenCompleto", () => {
  it("lista las ocho secciones del informe completo", () => {
    render(<ResumenCompleto secciones={ochoSecciones} dict={dict} />);
    // Un <h3> por sección: si el componente colapsara dos secciones en un
    // único bloque, o dejara de listar alguna, este conteo lo detecta.
    expect(screen.getAllByRole("heading", { level: 3 })).toHaveLength(8);
  });

  it("muestra cuántas palabras faltan por sección", () => {
    render(<ResumenCompleto secciones={ochoSecciones} dict={dict} />);
    // La sección "firma" todavía no se generó (parrafo vacío): lo que se
    // vende es que faltan sus 900 palabras completas.
    expect(screen.getByText(/900/)).toBeInTheDocument();
  });

  it("muestra el arranque de una sección ya generada", () => {
    render(<ResumenCompleto secciones={ochoSecciones} dict={dict} />);
    // Sin esta aserción, borrar el `{s.parrafo && <p>...}` del componente no
    // haría fallar ningún otro test: nada más comprueba que el párrafo se
    // pinte cuando existe.
    expect(screen.getByText(/Mercurio en tu carta habla de/)).toBeInTheDocument();
  });

  it("no se muestra si la carta ya tiene el informe completo", () => {
    // La página no llama al backend (ni pasa datos) cuando `interpretations`
    // ya incluye "largo": ese caso llega acá como un arreglo vacío.
    const { container } = render(<ResumenCompleto secciones={[]} dict={dict} />);
    expect(container).toBeEmptyDOMElement();
  });
});
