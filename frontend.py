import streamlit as st
import os
import shutil
from analyst_Agent import upload_csv, workflow

st.set_page_config(page_title="AI Data Analyst", layout="wide")

st.title("Data-Analyst-Agent")

# ---------------- File Upload Section ----------------
uploaded_file = st.file_uploader("Upload CSV File", type=["csv"])

if uploaded_file is not None:

    # Save uploaded file locally
    os.makedirs("temp", exist_ok=True)
    local_path = os.path.join("temp", uploaded_file.name)

    with open(local_path, "wb") as f:
        f.write(uploaded_file.getbuffer())

    st.success("CSV Uploaded Successfully")

    if st.button("Run Analysis"):

        with st.spinner("Running Data Analysis Workflow..."):

            # Clean old outputs
            if os.path.exists("downloaded_plots"):
                shutil.rmtree("downloaded_plots")

            # Upload CSV to Daytona sandbox
            upload_csv(local_path)

            # Run LangGraph workflow
            result = workflow.invoke({"last_step": "start"})

            final_analysis = result["final_analysis"]

        st.success("Analysis Completed")

        # ---------------- Display Final Analysis ----------------
        st.markdown("## Final Analysis Report")
        st.markdown(final_analysis)

        # ---------------- Display Generated Plots ----------------
        st.markdown("## Generated Visualizations")

        plot_folder = "downloaded_plots"

        if os.path.exists(plot_folder):
            plot_files = [
                f for f in os.listdir(plot_folder)
                if f.lower().endswith((".png", ".jpg", ".jpeg"))
            ]

            for plot in plot_files:
                st.image(
                    os.path.join(plot_folder, plot),
                    caption=plot,
                    use_column_width=True
                )
        else:
            st.warning("No plots were generated.")