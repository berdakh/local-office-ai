import WorkflowRunner from "../components/WorkflowRunner";
import { announcementStarters } from "../data/starters";

export default function Announcements() {
  return (
    <WorkflowRunner
      workflowId="announcements"
      title="Announcement Hub"
      description="Paste the week's announcements in any shape. Get bulletin, newsletter, email, social and slide versions."
      inputName="raw"
      inputLabel="Raw announcements"
      starters={announcementStarters}
      placeholder="fall festival sat 18th 4-7pm back lawn, need 6 trunks..."
    />
  );
}
