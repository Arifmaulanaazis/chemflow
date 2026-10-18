import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { it, expect, vi, afterEach } from "vitest";
import { fitStructure } from "../src/lib/ngl";
import { inputUploads } from "../src/lib/uploads";
import type { Job, Artifact } from "../src/lib/types";
import RunWorkspace from "../src/features/RunWorkspace";
import MoleculeViewer from "../src/features/MoleculeViewer";
vi.mock("../src/features/ArtifactBrowser", () => ({ default: () => <div>Files</div> }));
vi.mock("../src/features/InputRequests", () => ({ default: () => null }));
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); });
it("fits all camera rotations in portrait and ignores hidden canvases", () => {
  const zoomMove = vi.fn();
  const stage = { handleResize: vi.fn(), viewer: { width: 300, height: 600, perspectiveCamera: { fov: 40 } }, animationControls: { zoomMove } };
  const component = { getBox: () => ({ min: { distanceTo: () => 100 }, max: {} }), getCenter: () => [1,2,3] };
  fitStructure(stage, component);
  const halfAngle = Math.atan(Math.tan(20 * Math.PI / 180) * .5);
  expect(-zoomMove.mock.calls[0][1] * Math.sin(halfAngle)).toBeGreaterThan(52);
  stage.viewer.width = 0; fitStructure(stage, component);
  expect(zoomMove).toHaveBeenCalledTimes(1);
});
it("filters uploads by purpose and format, collapses names, keeps selections", () => {
  const uploads = [
    { id: "old/a.xlsx", name: "a.xlsx", size: 1, purpose: "ligands" },
    { id: "new/a.xlsx", name: "a.xlsx", size: 2, purpose: "ligands" },
    { id: "rec/r.xlsx", name: "r.xlsx", size: 1, purpose: "receptors" },
    { id: "p/p.pdb", name: "p.pdb", size: 1 }];
  expect(inputUploads(uploads, "ligands", undefined).map(f => f.id)).toEqual(["new/a.xlsx"]);
  expect(inputUploads(uploads, "ligands", "old/a.xlsx").map(f => f.id)).toEqual(["old/a.xlsx"]);
  expect(inputUploads(uploads, "receptors", undefined).map(f => f.id)).toEqual(["rec/r.xlsx"]);
});
it("shows indeterminate progress while running and 100 only after success", () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok:true, json:async()=>({text:""}) }));
  const job: Job = {id:"j1",name:"Docking",command:"run",status:"running",created:1,started:1,finished:null,exit_code:null,stage:"docking"};
  const props = {onBack:vi.fn(),onResume:vi.fn()};
  const {rerender} = render(<RunWorkspace job={job} {...props}/>);
  expect(screen.getByRole("progressbar")).not.toHaveAttribute("aria-valuenow");
  expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuetext","docking");
  rerender(<RunWorkspace job={{...job,pending_input:true}} {...props}/>);
  expect(screen.getByRole("progressbar")).toHaveClass("waiting");
  rerender(<RunWorkspace job={{...job,status:"succeeded"}} {...props}/>);
  expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow","100");
  rerender(<RunWorkspace job={{...job,status:"failed"}} {...props}/>);
  expect(screen.queryByRole("progressbar")).not.toBeInTheDocument();
});
it("loads the docking gridbox and uses the same camera distance for Fit and Reset", async () => {
  vi.stubGlobal("ResizeObserver", class { observe() {} disconnect() {} });
  const zoomMove=vi.fn(), rotate=vi.fn();
  const component={structure:{modelStore:{count:1}},getBox:()=>({min:{distanceTo:()=>70},max:{}}),getCenter:()=>[1,2,3],addRepresentation:vi.fn(),removeAllRepresentations:vi.fn(),setSelection:vi.fn()};
  class Stage {
    viewer={width:600,height:400,perspectiveCamera:{fov:40}};
    animationControls={zoomMove,rotate}; signals={clicked:{add:vi.fn()}};
    handleResize=vi.fn(); dispose=vi.fn(); loadFile=async()=>component;
    addComponentFromObject=()=>({addRepresentation:vi.fn()}); removeComponent=vi.fn();
  }
  class Shape {addCylinder() {} addSphere() {}}
  vi.stubGlobal("NGL",{Stage,Shape});
  vi.stubGlobal("fetch",vi.fn().mockResolvedValue({ok:true,json:async()=>({coordinates:[12,-8,4,20,22,24]}),blob:async()=>new Blob(["END"])}));
  const file:Artifact={path:"complexes/R/ligand_complex.pdb",extension:".pdb",size:1,modified:1};
  render(<MoleculeViewer jobId="j1" file={file}/>);
  await waitFor(()=>expect(screen.getByRole("button",{name:"Fit"})).toBeEnabled());
  fireEvent.click(screen.getByLabelText("Gridbox",{exact:true}));
  expect(screen.getByLabelText("Center X (Å)")).toHaveValue(12);
  expect(screen.getByLabelText("Center Y (Å)")).toHaveValue(-8);
  expect(screen.getByLabelText("Size Z (Å)")).toHaveValue(24);
  fireEvent.click(screen.getByRole("button",{name:"Fit"}));
  const fit=zoomMove.mock.calls.at(-1);
  fireEvent.click(screen.getByRole("button",{name:"Reset"}));
  expect(zoomMove.mock.calls.at(-1)).toEqual(fit);
  expect(rotate).toHaveBeenCalledWith([0,0,0,1],0);
});
