// Keep examples tied to the same source revision as the model adapter.
export const EXAMPLE_SOURCE = "https://raw.githubusercontent.com/code-video-model/CodeVideoModel/5f3bdc665246ca19861853144b7639495c510118/examples";
export const EXAMPLES = [
  {id: "chair_placement/original", title: "Sunlit study", proxy: "proxy.mp4", description: "A camera move through a furnished study."},
  {id: "chair_placement/edited", title: "Study · edited layout", proxy: "proxy.mp4", description: "The authors' alternate chair arrangement."},
  {id: "robot_navigation", title: "Robot navigation", proxy: "code_video.mp4", description: "A robot moving through an indoor scene."},
  {id: "loft_tour", title: "Loft tour", proxy: "code_video.mp4", description: "Explore an architectural interior."},
  {id: "tank_boarding", title: "Tank boarding", proxy: "code_video.mp4", description: "A character boarding a tracked vehicle."},
] as const;

export async function loadExample(id: string) {
  const example = EXAMPLES.find(example => example.id === id);
  if (!example) throw new Error("Unknown example");
  const get = async (name: string) => {
    const response = await fetch(`${EXAMPLE_SOURCE}/${id}/${name}`, {signal: AbortSignal.timeout(60000)});
    if (!response.ok) throw new Error(`Could not load ${name} (HTTP ${response.status}). Try again or upload your own files.`);
    return response;
  };
  const [proxy, reference, prompt] = await Promise.all([
    get(example.proxy).then(r => r.blob()),
    get("reference.png").then(r => r.blob()),
    get("prompt.txt").then(r => r.text()),
  ]);
  if (!proxy.size || !reference.size || !prompt.trim()) throw new Error("Example files are incomplete. Try again or upload your own files.");
  return {proxy: new File([proxy], "code_video.mp4", {type: "video/mp4"}),
    reference: new File([reference], "reference.png", {type: "image/png"}), prompt};
}
