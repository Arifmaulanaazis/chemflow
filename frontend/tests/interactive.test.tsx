import { useState } from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import Select from "../src/components/atoms/Select";
import { boxVertices, gridShape } from "../src/lib/gridbox";

it("keyboard selection starts at the selected value and skips disabled options", () => {
  function Field() {
    const [value, setValue] = useState("b");
    return <Select aria-label="Native" value={value} onChange={e=>setValue(e.target.value)}>
      <option value="a">Alpha</option><option value="b">Beta</option>
      <option value="c" disabled>Blocked</option><option value="d">Delta</option>
    </Select>;
  }
  render(<Field/>);
  const trigger=screen.getByRole("combobox");
  fireEvent.keyDown(trigger,{key:"Enter"});
  fireEvent.keyDown(trigger,{key:"ArrowDown"});
  fireEvent.keyDown(trigger,{key:"Enter"});
  expect(trigger).toHaveTextContent("Delta");
  expect(trigger).toHaveAttribute("aria-expanded","false");
  fireEvent.keyDown(trigger,{key:"Enter"});
  fireEvent.keyDown(trigger,{key:"Home"});
  fireEvent.keyDown(trigger,{key:"Escape"});
  expect(trigger).toHaveTextContent("Delta");
});

it("multiple selection toggles native option values without closing the list", () => {
  const changed=vi.fn();
  function Field(){const [value,setValue]=useState(["a"]);return <Select multiple aria-label="Files" value={value} onChange={e=>{const next=Array.from(e.target.selectedOptions,o=>o.value);changed(next);setValue(next)}}><option value="a">Alpha</option><option value="b">Beta</option></Select>}
  render(<Field/>);
  const trigger=screen.getByRole("combobox");fireEvent.click(trigger);
  fireEvent.click(screen.getByRole("option",{name:"Beta"}));
  expect(changed).toHaveBeenLastCalledWith(["a","b"]);
  expect(trigger).toHaveAttribute("aria-expanded","true");
  fireEvent.click(screen.getByRole("option",{name:"Alpha"}));
  expect(changed).toHaveBeenLastCalledWith(["b"]);
});

it("Vina box geometry has eight corners, twelve unique edges and a center marker",()=>{
  const coords=[-2,4,6,20,24,30];const corners=boxVertices(coords);
  expect(corners).toHaveLength(8);expect(new Set(corners.map(v=>v.join(","))).size).toBe(8);
  expect(corners[0]).toEqual([-12,-8,-9]);expect(corners[7]).toEqual([8,16,21]);
  const cylinder=vi.fn(),sphere=vi.fn();
  class Shape{addCylinder=cylinder;addSphere=sphere}
  expect(gridShape({Shape},coords)).toBeInstanceOf(Shape);
  expect(cylinder).toHaveBeenCalledTimes(12);expect(sphere).toHaveBeenCalledWith([-2,4,6],expect.any(Array),.35);
  for(const [a,b] of cylinder.mock.calls)expect(a.filter((v:number,i:number)=>v!==b[i])).toHaveLength(1);
  expect(boxVertices([0,0,0,-1,2,3])).toEqual([]);expect(boxVertices([NaN,0,0,1,2,3])).toEqual([]);
});
