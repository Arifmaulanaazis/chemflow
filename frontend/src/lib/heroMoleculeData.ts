/** Karya hero asli: graf ilustratif, bukan struktur eksperimen. */
export const heroNodes = [
  {x:128,y:153,z:-.1,color:0,radius:12},
  {x:168,y:89,z:.15,color:0,radius:12},
  {x:240,y:91,z:.25,color:0,radius:12},
  {x:281,y:151,z:.1,color:0,radius:12},
  {x:244,y:215,z:-.2,color:0,radius:12},
  {x:173,y:215,z:-.25,color:0,radius:12},
  {x:350,y:145,z:.55,color:1,radius:15},
  {x:380,y:87,z:.85,color:2,radius:15},
  {x:279,y:263,z:-.6,color:2,radius:15},
  {x:145,y:38,z:-.45,color:1,radius:15},
  {x:72,y:166,z:.35,color:2,radius:15},
  {x:274,y:40,z:-.3,color:1,radius:15},
] as const;
export const heroLinks = [
  [0,1],[1,2],[2,3],[3,4],[4,5],[5,0],
  [3,6],[6,7],[4,8],[1,9],[0,10],[2,11],
] as const;
