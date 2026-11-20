// Ein einziges Werkzeug fuer pi: den fertigen Bildprompt an den Bildermacher
// uebergeben. Das Werkzeug selbst tut nichts -- der Server liest den Aufruf
// aus dem RPC-Strom (tool_execution_start) und reicht ihn an die Seite
// weiter. So braucht pi weder eine Adresse noch einen Schluessel.
import { Type } from "typebox";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

export default function (pi: ExtensionAPI) {
	pi.registerTool({
		name: "bildprompt_senden",
		label: "Bildprompt senden",
		description:
			"Uebergibt den fertigen Bildprompt an das Feld Text->Bild des Bildermachers. " +
			"Nur aufrufen, wenn der Benutzer ausdruecklich senden/uebernehmen/fertig sagt.",
		promptSnippet: "bildprompt_senden: fertigen Bildprompt an Text->Bild uebergeben",
		parameters: Type.Object({
			prompt: Type.String({ description: "Der Bildprompt auf Englisch. Variablen als #name#, die Bezugsperson als !Name!." }),
			negative_prompt: Type.Optional(Type.String({ description: "Was nicht ins Bild soll, kommagetrennt" })),
			aspect: Type.Optional(Type.String({ description: "Seitenverhaeltnis, z. B. 1:1, 3:4, 16:9" })),
			style: Type.Optional(Type.String({ description: "Schluessel aus der Stil-Liste" })),
			light: Type.Optional(Type.String({ description: "Schluessel aus der Licht-Liste" })),
			camera: Type.Optional(Type.String({ description: "Schluessel aus der Kamera-Liste" })),
			view: Type.Optional(Type.String({ description: "Schluessel aus der Blickwinkel-Liste" })),
			count: Type.Optional(Type.Number({ description: "Anzahl Bilder, 1 bis 20" })),
			variablen: Type.Optional(
				Type.Record(Type.String(), Type.Array(Type.String()), {
					description: "Werte je Variable, z. B. {\"hose\": [\"jeans\", \"shorts\"]}",
				}),
			),
		}),
		async execute(_id, _params) {
			return {
				content: [{ type: "text", text: "Uebergeben. Der Prompt steht jetzt im Feld Text->Bild." }],
				details: {},
			};
		},
	});
}
