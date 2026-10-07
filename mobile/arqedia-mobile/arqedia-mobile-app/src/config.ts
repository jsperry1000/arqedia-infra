// What this build points at. The same literals as ui/src/config.ts, and wrong
// for a second environment in the same way (ENV-01).
//
// THE WEB CLIENT, REUSED. API Gateway's JWT authorizer accepts tokens for one
// audience, the web client (api.tf), so the app signs in through it. A
// mobile client of its own - its own audience, revocable on its own - is a
// Terraform change and is not made here.
export const config = {
  userPoolId: 'us-east-2_AcsEyzDLL',
  userPoolClientId: '7neoek1vpj90suoo8p8rrp04re',
  apiUrl: 'https://o4fofn0ez5.execute-api.us-east-2.amazonaws.com',
};
