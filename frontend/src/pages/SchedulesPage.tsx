import { useParams } from "react-router-dom";
import { ScheduleCalendar } from "@/components/schedules/ScheduleCalendar";

/** Mounted at BOTH /schedules (personal, spans all workspaces) and
 * /w/:workspace/schedules (that workspace). Same component; the workspace
 * filter is only meaningful — and only shown — on the personal route, since the
 * tenant route is already one workspace. The api client picks the scope from
 * the URL automatically. */
export default function SchedulesPage() {
  const { workspace } = useParams();
  return <ScheduleCalendar showWorkspaceFilter={!workspace} />;
}
