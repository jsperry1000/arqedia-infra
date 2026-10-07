// A hand-kept TypeScript mirror of ui/src/tokens.css, which is the single
// source for every colour. React Native cannot import CSS, so these values
// are copied from it, not declared here: when tokens.css changes, update this
// file by hand to match. A colour that is not in tokens.css does not belong
// here; it is added to tokens.css first.
export const colors = {
  deep: '#002561', // --deep
  mid: '#278ACA', // --medium
  light: '#C7E4F8', // --light
  // reserved for the generate control only — do not use elsewhere.
  highlight: '#FFDD00', // --gold

  ink: '#0d1b2a', // --ink
  subtext: '#3c4a5c', // --ink-2
  muted: '#64748b', // --muted
  border: '#e2e8f0', // --line
  surface: '#ffffff', // --paper
  background: '#f7fafd', // --wash
  shade: '#eef4fa', // --shade
} as const;
